"""Motor orquestador de cartera: une market data, estrategias (una por símbolo),
riesgo y ejecución, sobre un balance compartido.

- `process(symbol, candles)` = un ciclo de decisión para UN símbolo.
- `run()` recorre todos los instrumentos en bucle (modo live/paper continuo).

Cada cierre de posición se persiste como un `ClosedTrade` con su P&L, que es lo
que luego se consulta para juzgar la viabilidad.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from .config import Config, Instrument
from .execution.base import ExecutionEngine, OrderRejected
from .models import ClosedTrade, Order, Position, Side, SignalType
from .notifier import Notifier, NullNotifier
from .regime import classify_regime
from .risk import RiskManager
from .storage import Storage
from .strategy.base import Strategy

logger = logging.getLogger(__name__)

# Salidas que cuentan como "strike" (si además cierran en pérdida).
STRIKE_EXIT_REASONS = ("stop-loss", "trailing-stop")


# Antes de vender, el libro de órdenes debe estar como mucho a esto del precio que disparó la salida.
EXIT_CONFIRM_TOLERANCE = 0.01
UNPROTECTED_ALERT_SECONDS = 900.0     # avisar si una posición lleva este tiempo sin stop en el exchange
URGENT_EXITS = ("stop-loss", "trailing-stop")


class ForeignPositionsError(RuntimeError):
    """Hay posiciones abiertas registradas que pertenecen a otro exchange."""


class Engine:
    def __init__(
        self,
        config: Config,
        strategies: dict[str, Strategy],
        risk: RiskManager,
        execution: ExecutionEngine,
        storage: Storage,
        exchange=None,
        enforce_daily_loss: bool = True,
        notifier: Notifier | None = None,
        head_log_dir: str | None = None,
        max_hold_bars: int = 0,
        enforce_pause_rules: bool = True,
    ):
        self.config = config
        self.strategies = strategies
        self.risk = risk
        self.execution = execution
        self.storage = storage
        self.exchange = exchange
        self.enforce_daily_loss = enforce_daily_loss
        self.notifier = notifier or NullNotifier()
        self.head_log_dir = head_log_dir
        self.max_hold_bars = max_hold_bars   # 0 = sin tope de tiempo
        # Las pausas van contra el reloj real: el backtester las desactiva.
        self.enforce_pause_rules = enforce_pause_rules
        self.positions: list[Position] = []
        self.last_prices: dict[str, float] = {}
        self.closed_trades: list[ClosedTrade] = []
        self._unconfirmed: list[dict] = []   # ejecuciones con datos estimados, por confirmar
        self._orphan_alert_at = 0.0          # último aviso de órdenes huérfanas no cancelables
        self._unprotected_alert_at = 0.0     # último aviso de posiciones sin stop en el exchange
        from .exchange_stops import StopGuard
        eng = getattr(config, "engine", None)
        stops_on = (getattr(config, "mode", "") == "live" and exchange is not None
                    and getattr(eng, "exchange_stops", False) is True)
        self.stop_guard = StopGuard(
            exchange,
            buffer_pct=float(eng.exchange_stop_buffer_pct) if stops_on else 0.0,
            min_move_pct=float(eng.exchange_stop_min_move_pct) if stops_on else 0.0,
            enabled=stops_on,
        )

    # --- Ciclo de decisión de un símbolo -------------------------------------------

    def process(self, symbol: str, candles: pd.DataFrame) -> None:
        current_price = float(candles["close"].iloc[-1])
        if not getattr(self.config, "signals_elsewhere", False):
            # Con las velas de otro exchange, su cierre no es el precio de aquí: las salidas
            # y el precio de referencia los pone el exchange que opera (ver daemon).
            self.last_prices[symbol] = current_price
            self._check_exits(symbol, current_price, candles=candles)
        self._check_entry(symbol, candles, current_price)

        if self.enforce_daily_loss:
            self.risk.register_equity(self.equity())
            
            # Persistir nueva ATH en la base de datos
            ath_db = self.storage.get_state("ath_equity", 0.0) or 0.0
            if self.risk.ath_equity > ath_db:
                self.storage.set_state("ath_equity", self.risk.ath_equity)
                
            # Disyuntor global de pérdida de cuenta
            if self.risk.halted and self.risk.halted_reason == "drawdown_cuenta" and len(self.positions) > 0:
                logger.critical("[DISYUNTOR] Drawdown global crítico de cuenta alcanzado. Cerrando todo.")
                self.notifier.notify_circuit_breaker(
                    self.risk.global_drawdown,
                    getattr(self.config.risk, "max_account_drawdown_pct", 0.15),
                )
                self.emergency_close_all(reason="global_drawdown_halt")

        self._rebalance_hedging()

    def _rebalance_hedging(self) -> None:
        if not hasattr(self.config, "hedging") or not self.config.hedging.enabled:
            return

        hedge_cfg = self.config.hedging
        hedge_symbol = hedge_cfg.symbol

        # Calcular exposición de altcoins (excluyendo el propio símbolo de cobertura)
        total_alt_exposure = 0.0
        num_alt_positions = 0
        for pos in self.positions:
            if pos.symbol == hedge_symbol:
                continue
            current_price = self.last_prices.get(pos.symbol, pos.entry_price)
            pos_val = current_price * pos.amount
            if pos.side is Side.BUY:
                total_alt_exposure += pos_val
                num_alt_positions += 1
            else:
                total_alt_exposure -= pos_val

        # Determinar el precio de la cobertura (BTC/USDT)
        btc_price = self.last_prices.get(hedge_symbol)
        if btc_price is None and self.exchange is not None:
            try:
                btc_price = self.exchange.fetch_last_price(hedge_symbol)
                self.last_prices[hedge_symbol] = btc_price
            except Exception:
                pass

        if btc_price is None or btc_price <= 0:
            return

        # Calcular el tamaño objetivo del corto de cobertura
        if num_alt_positions >= hedge_cfg.min_positions:
            target_hedge_usd = total_alt_exposure * hedge_cfg.ratio
        else:
            target_hedge_usd = 0.0

        target_amount = target_hedge_usd / btc_price

        # Encontrar cobertura actual
        current_hedge_pos = None
        for pos in self.positions:
            if pos.symbol == hedge_symbol and pos.side is Side.SELL:
                current_hedge_pos = pos
                break

        current_amount = current_hedge_pos.amount if current_hedge_pos else 0.0
        diff_amount = target_amount - current_amount

        # Decidir si la diferencia es significativa
        significant = False
        if target_amount > 0:
            diff_pct = abs(diff_amount) / target_amount
            diff_usd = abs(diff_amount) * btc_price
            if (current_amount == 0) or (diff_pct > 0.15 and diff_usd > 15.0):
                significant = True
        elif current_amount > 0:
            significant = True

        if not significant:
            return

        logger.info(
            "[HEDGE] Ajustando cobertura: alt_exp=%.2f, target_usd=%.2f, target_amt=%.6f, current_amt=%.6f",
            total_alt_exposure, target_hedge_usd, target_amount, current_amount
        )

        # 1) Cerrar cobertura existente si la hay
        if current_hedge_pos:
            close_side = Side.BUY
            reason = "hedge_close" if target_amount == 0 else "hedge_adjust_close"
            close_order = Order(hedge_symbol, close_side, current_amount, btc_price, reason=reason)
            if self._close_position(current_hedge_pos, close_order):
                self.positions = [p for p in self.positions if p is not current_hedge_pos]

        # 2) Abrir nueva cobertura si es necesario
        if target_amount > 0:
            reason = "hedge_open" if current_amount == 0 else "hedge_adjust_open"
            order = Order(hedge_symbol, Side.SELL, target_amount, btc_price, reason=reason)
            try:
                fill = self.execution.execute(order)
                self.storage.record_fill(fill)
                
                # Obtener o construir Instrument para la cobertura
                instrument = None
                try:
                    instrument = self.config.instrument(hedge_symbol)
                except KeyError:
                    pass
                if not instrument:
                    instrument = Instrument(
                        symbol=hedge_symbol, category="hedging", strategy_name="hedge",
                        strategy_params={}, stop_loss_pct=0.5, take_profit_pct=0.5,
                        position_size_pct=0.0, timeframe="1h"
                    )
                position = self.risk.build_position(
                    instrument, Side.SELL, fill.filled_amount,
                    fill.filled_price, fill.fee, reason
                )
                self.positions.append(position)
                self.storage.save_open_position(position)
                self._save_cash()
                logger.info(
                    "[HEDGE] Nueva cobertura corta BTC abierta: %.4f @ %.2f",
                    fill.filled_amount, fill.filled_price
                )
                self.notifier.notify(
                    f"🛡️ <b>ABRE COBERTURA</b> SHORT {hedge_symbol}\n"
                    f"Precio: {fill.filled_price:.2f}  |  Tamaño: {fill.filled_amount:.6f}\n"
                    f"Motivo: {reason}"
                )
            except Exception as e:
                logger.warning("[HEDGE] No se pudo abrir la cobertura: %s", e)

    def _check_exits(self, symbol: str, current_price: float, candles: pd.DataFrame | None = None,
                     count_bar: bool = True) -> None:
        """`count_bar=False` en el sondeo rápido entre ciclos: evalúa las salidas sin
        contar una vela más de permanencia."""
        current_atr = 0.0
        if candles is not None and len(candles) >= 15:
            try:
                from .indicators import atr
                current_atr = float(atr(candles["high"], candles["low"], candles["close"], 14).iloc[-1])
            except Exception:
                current_atr = 0.0

        still_open: list[Position] = []
        for pos in self.positions:
            if pos.symbol != symbol:
                still_open.append(pos)
                continue
            if count_bar:
                pos.bars_held += 1
            # 1) Salida por TIEMPO (si está activada): cerrar tras N velas.
            if self.max_hold_bars and pos.bars_held >= self.max_hold_bars:
                close_side = Side.SELL if pos.side is Side.BUY else Side.BUY
                order = Order(pos.symbol, close_side, pos.amount, current_price, reason="timeout")
                if self._close_position(pos, order):
                    continue
                self.storage.update_open_position(pos)
                still_open.append(pos)
                continue
            # 2) Salida por TP / SL / trailing / partial-TP (evaluate_exit muta trailing/peak).
            before = (pos.stop_loss, pos.peak_price)
            decision = self.risk.evaluate_exit(pos, current_price, current_atr=current_atr)
            if decision.order is not None and not self._exit_confirmed(pos, decision.order):
                # El precio que pedía vender no se sostiene en el libro: tampoco vale para
                # arrastrar el stop. Se deja todo como estaba y se vuelve a mirar en el siguiente sondeo.
                pos.stop_loss, pos.peak_price = before
                self.storage.update_open_position(pos)
                still_open.append(pos)
                continue
            if decision.order is not None:
                if decision.order.reason == "partial-take-profit":
                    executed = self._stop_already_executed(pos)
                    if executed:
                        continue  # la vendió antes el stop del exchange
                    if executed is False and self._execute_partial_close(pos, decision.order):
                        self.storage.update_open_position(pos)
                        self._sync_stop(pos)   # nueva cantidad y stop en la entrada
                        still_open.append(pos)
                        continue
                elif self._close_position(pos, decision.order):
                    continue  # cerrada con éxito -> no se mantiene
            self.storage.update_open_position(pos)   # persistir trailing/bars_held/partial_tp
            self._sync_stop(pos)                     # el stop del exchange sigue al del bot
            still_open.append(pos)
        self.positions = still_open

    def _exit_confirmed(self, pos: Position, order: Order) -> bool:
        """Segunda lectura antes de vender (solo en real): el libro de órdenes debe
        respaldar el precio que disparó la salida. Un precio de ticker o de vela que no
        existió en el mercado no debe provocar una venta.
          - stop: se vende salvo que el libro esté claramente POR ENCIMA de ese precio;
          - objetivo o toma parcial: se vende solo si el libro NO está claramente por debajo.
        Si la lectura falla, un stop se ejecuta igualmente (lo urgente es salir) y el
        resto espera al siguiente sondeo."""
        urgent = order.reason in URGENT_EXITS
        if order.reason not in URGENT_EXITS + ("take-profit", "partial-take-profit"):
            return True
        fetch = getattr(self.exchange, "fetch_book_price", None)
        if self.config.mode != "live" or not callable(fetch):
            return True
        try:
            book = float(fetch(pos.symbol, order.side.value))
        except Exception as exc:
            logger.warning("[%s] No pude confirmar en el libro la salida %s de %s (precio visto %.6f): %s; %s",
                           pos.category, order.reason, pos.symbol, order.price, exc,
                           "vendo igualmente" if urgent else "espero al siguiente sondeo")
            return urgent
        selling = order.side is Side.SELL
        price_fell = urgent if selling else not urgent        # ¿la salida la provoca una caída del precio?
        if price_fell:
            confirmed = book <= order.price * (1 + EXIT_CONFIRM_TOLERANCE)
        else:
            confirmed = book >= order.price * (1 - EXIT_CONFIRM_TOLERANCE)
        if confirmed:
            logger.info("[%s] salida %s de %s: precio visto %.6f, libro %.6f",
                        pos.category, order.reason, pos.symbol, order.price, book)
        else:
            logger.warning("[%s] Salida %s de %s NO confirmada: precio visto %.6f pero el libro está en %.6f "
                           "(%+.2f%%); no vendo y vuelvo a mirar en el siguiente sondeo",
                           pos.category, order.reason, pos.symbol, order.price, book, (book / order.price - 1) * 100)
        return confirmed

    def update_head_symbols(self, category: str, new_symbols: list[str]) -> None:
        """Actualiza los símbolos de una cabeza (p.ej. tras selección RS), creando
        estrategias e instrumentos sin cerrar posiciones previas de símbolos antiguos."""
        from .strategy import build_strategy

        sample_ins = None
        for ins in self.config.instruments:
            if ins.category == category:
                sample_ins = ins
                break
        if not sample_ins:
            return

        old_instruments = [ins for ins in self.config.instruments if ins.category == category]
        remaining = [ins for ins in self.config.instruments if ins.category != category]

        new_instruments = []
        for sym in new_symbols:
            existing = next((ins for ins in old_instruments if ins.symbol == sym), None)
            if existing:
                new_instruments.append(existing)
            else:
                new_ins = Instrument(
                    symbol=sym,
                    category=category,
                    strategy_name=sample_ins.strategy_name,
                    strategy_params=dict(sample_ins.strategy_params),
                    stop_loss_pct=sample_ins.stop_loss_pct,
                    take_profit_pct=sample_ins.take_profit_pct,
                    position_size_pct=sample_ins.position_size_pct,
                    trailing_stop_pct=sample_ins.trailing_stop_pct,
                    partial_take_profit_pct=sample_ins.partial_take_profit_pct,
                    partial_take_profit_ratio=sample_ins.partial_take_profit_ratio,
                    max_concurrent_per_symbol=sample_ins.max_concurrent_per_symbol,
                    regimes=list(sample_ins.regimes),
                    regime_volatile_atr_pct=sample_ins.regime_volatile_atr_pct,
                    timeframe=sample_ins.timeframe,
                    dynamic_rs_enabled=sample_ins.dynamic_rs_enabled,
                    rs_pool=list(sample_ins.rs_pool),
                    rs_top_k=sample_ins.rs_top_k,
                    rs_lookback_days=sample_ins.rs_lookback_days,
                    rs_hysteresis_pct=sample_ins.rs_hysteresis_pct,
                    macro_btc_filter=sample_ins.macro_btc_filter,
                    asset_trend_ema=sample_ins.asset_trend_ema,
                    use_atr_trailing=sample_ins.use_atr_trailing,
                    atr_trailing_mult=sample_ins.atr_trailing_mult,
                    volatility_sizing=sample_ins.volatility_sizing,
                    volatility_ref_atr_pct=sample_ins.volatility_ref_atr_pct,
                    volatility_size_min=sample_ins.volatility_size_min,
                    volatility_size_max=sample_ins.volatility_size_max,
                    strong_close_filter=sample_ins.strong_close_filter,
                    strong_close_threshold=sample_ins.strong_close_threshold,
                    strike_limit=sample_ins.strike_limit,
                    strike_window_days=sample_ins.strike_window_days,
                    strike_pause_days=sample_ins.strike_pause_days,
                    paused_while_open=list(sample_ins.paused_while_open),
                )
                new_instruments.append(new_ins)

        self.config.instruments = remaining + new_instruments

        for ins in new_instruments:
            if ins.symbol not in self.strategies:
                self.strategies[ins.symbol] = build_strategy(ins.strategy_name, ins.strategy_params)

    def _check_entry(self, symbol: str, candles: pd.DataFrame, current_price: float) -> None:
        strategy = self.strategies[symbol]
        signal = strategy.generate_signal(symbol, candles)
        if signal.type is SignalType.HOLD:
            return

        instrument = self.config.instrument(symbol)
        head = f"{instrument.category}/{instrument.strategy_name}"

        # Reglas de pausa de la cabeza (strikes / otra cabeza con posiciones).
        if self.enforce_pause_rules:
            paused = self._entry_pause_reason(instrument)
            if paused:
                logger.info("[%s] Entrada en %s omitida: %s", head, symbol, paused)
                return

        # Filtro Macro de BTC: congela nuevas compras en altcoins si BTC < EMA50
        if getattr(instrument, "macro_btc_filter", False):
            from .regime import is_btc_macro_bullish
            if not is_btc_macro_bullish(self.exchange, self.config.reference_symbol):
                logger.info("[%s] Compras pausadas en %s (Filtro Macro BTC: BTC < EMA50)", head, symbol)
                return

        # Filtro de tendencia de la propia moneda: precio >= su EMA diaria de N velas.
        trend_ema = getattr(instrument, "asset_trend_ema", 0)
        if isinstance(trend_ema, (int, float)) and trend_ema > 0:
            from .regime import is_above_daily_ema
            if not is_above_daily_ema(self.exchange, symbol, int(trend_ema)):
                logger.info("[%s] Entrada en %s omitida: precio bajo su EMA%d diaria", head, symbol, int(trend_ema))
                return

        # Filtro de régimen: la cabeza solo entra si el mercado le favorece.
        if instrument.regimes:
            if instrument.regime_volatile_atr_pct is not None:
                regime = classify_regime(
                    candles, volatile_atr_pct=instrument.regime_volatile_atr_pct
                )
            else:
                regime = classify_regime(candles)
            if regime not in instrument.regimes:
                logger.debug("[%s] %s no opera en régimen '%s'", symbol, head, regime)
                return

        # Filtro de Cierre Fuerte: rechaza entradas en velas con mecha de rechazo.
        if getattr(instrument, "strong_close_filter", False) and len(candles) >= 1:
            last = candles.iloc[-1]
            candle_range = last["high"] - last["low"]
            if candle_range > 0:
                threshold = getattr(instrument, "strong_close_threshold", 0.75)
                close_position_in_range = (last["close"] - last["low"]) / candle_range
                if signal.type is SignalType.BUY and close_position_in_range < threshold:
                    logger.info(
                        "[%s] Entrada BUY rechazada por cierre débil (%.1f%% del rango, mínimo %.0f%%)",
                        symbol, close_position_in_range * 100, threshold * 100,
                    )
                    return
                if signal.type is SignalType.SELL and close_position_in_range > (1 - threshold):
                    logger.info(
                        "[%s] Entrada SELL rechazada por cierre débil (%.1f%% del rango)",
                        symbol, close_position_in_range * 100,
                    )
                    return

        # Calcular ATR para volatility sizing
        current_atr = 0.0
        if len(candles) >= 15:
            try:
                from .indicators import atr as calc_atr
                current_atr = float(calc_atr(candles["high"], candles["low"], candles["close"], 14).iloc[-1])
            except Exception:
                current_atr = 0.0

        balance = self.execution.get_balance()
        # Equity = USDT libre + valor de mercado de las posiciones (sin otra consulta al exchange).
        equity = balance + sum(
            (1 if p.side is Side.BUY else -1) * self.last_prices.get(p.symbol, p.entry_price) * p.amount
            for p in self.positions
        )
        decision = self.risk.evaluate_entry(
            signal, instrument, balance, self.positions, current_atr=current_atr, equity=equity,
        )
        if decision.order is None:
            logger.debug("[%s] entrada rechazada: %s", symbol, decision.reason)
            return

        try:
            fill = self.execution.execute(decision.order)
        except OrderRejected as e:
            logger.warning("[%s] entrada omitida por el exchange: %s", symbol, e)
            return
        self.storage.record_fill(fill)
        position = self.risk.build_position(
            instrument, decision.order.side, fill.filled_amount,
            fill.filled_price, fill.fee, signal.reason,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
        )
        self.positions.append(position)
        self.storage.save_open_position(position)   # persistir para reinicios
        self._track_unconfirmed("entry", fill, position=position)
        self._sync_stop(position)
        self._save_cash()
        quote = self.config.risk.quote_currency
        equity = self.equity()
        logger.info(
            "[%s] ABRE %s %s @ %.6f (SL %.6f / TP %.6f) | saldo=%.2f %s — %s",
            head, symbol, position.side.value, position.entry_price,
            position.stop_loss, position.take_profit, equity, quote, signal.reason,
        )
        self._log_head(instrument.category,
                       f"ABRE {position.side.value} {symbol} @ {position.entry_price:.6f} | saldo {equity:.2f} {quote} — {signal.reason}")
        self.notifier.notify_trade_opened(
            position=position,
            head=head,
            signal_reason=signal.reason,
            equity=equity,
            quote=quote,
        )

    # --- Reglas de pausa por cabeza ---------------------------------------------------

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _head_instrument(self, category: str) -> Instrument | None:
        for ins in self.config.instruments:
            if ins.category == category:
                return ins
        return None

    def _entry_pause_reason(self, instrument: Instrument) -> str | None:
        """Motivo por el que la cabeza no puede abrir ahora, o None si puede."""
        # Pausa manual del operador (manage.py pause/resume): vale para cualquier cabeza.
        from .pause_control import describe_until, manual_key
        key = manual_key(instrument.category)
        manual = self.storage.get_state(key) or 0.0
        if manual:
            if self._now().timestamp() < manual:
                return f"en pausa manual {describe_until(manual)}"
            self.storage.set_state(key, 0.0)              # pausa cumplida
            logger.info("[%s] Pausa manual cumplida: vuelve a operar", instrument.category)
            self.notifier.notify(
                f"▶️ <b>Cabeza reanudada</b>: {instrument.category}\n"
                "Termina la pausa manual; vuelve a poder abrir posiciones."
            )

        for other in instrument.paused_while_open:
            if any(p.category == other for p in self.positions):
                return f"en pausa mientras {other} tenga posiciones abiertas"

        if instrument.strike_limit > 0:
            key = f"pause_until:{instrument.category}"
            until = self.storage.get_state(key) or 0.0
            if until:
                if self._now().timestamp() < until:
                    limit = datetime.fromtimestamp(until, tz=timezone.utc)
                    return f"en pausa por strikes hasta {limit:%Y-%m-%d %H:%M} UTC"
                self.storage.set_state(key, 0.0)          # pausa cumplida
                logger.info("[%s] Pausa por strikes cumplida: vuelve a operar", instrument.category)
                self.notifier.notify(
                    f"▶️ <b>Cabeza reanudada</b>: {instrument.category}\n"
                    "Termina la pausa por strikes; vuelve a poder abrir posiciones."
                )
        return None

    def _register_strike(self, trade: ClosedTrade) -> None:
        """Tras un stop con pérdida, pausa la cabeza si acumula `strike_limit`
        en `strike_window_days`. El estado se persiste (sobrevive a reinicios)."""
        if not self.enforce_pause_rules:
            return
        if trade.exit_reason not in STRIKE_EXIT_REASONS or trade.pnl_abs >= 0:
            return
        instrument = self._head_instrument(trade.category)
        if instrument is None or instrument.strike_limit <= 0:
            return

        head = instrument.category
        now = trade.closed_at
        if now.timestamp() < (self.storage.get_state(f"pause_until:{head}") or 0.0):
            return                                        # ya está en pausa
        window_start = now - timedelta(days=instrument.strike_window_days)
        # Los strikes que ya provocaron una pausa anterior no vuelven a contar.
        reset_at = self.storage.get_state(f"strike_reset:{head}") or 0.0
        strikes = sum(
            1 for t in self.storage.losing_stop_times(head, STRIKE_EXIT_REASONS)
            if t >= window_start and t.timestamp() > reset_at
        )
        if strikes < instrument.strike_limit:
            return

        until = now + timedelta(days=instrument.strike_pause_days)
        self.storage.set_state(f"pause_until:{head}", until.timestamp())
        self.storage.set_state(f"strike_reset:{head}", now.timestamp())
        logger.warning(
            "[%s] %d stops con pérdida en %g días: cabeza EN PAUSA hasta %s",
            head, strikes, instrument.strike_window_days, until.isoformat(timespec="minutes"),
        )
        self._log_head(head, f"PAUSA por strikes ({strikes} stops) hasta {until:%Y-%m-%d %H:%M} UTC")
        self.notifier.notify(
            f"⏸️ <b>Cabeza en pausa</b>: {head}\n"
            f"{strikes} stops con pérdida en {instrument.strike_window_days:g} días. "
            f"No abrirá posiciones nuevas hasta el {until:%Y-%m-%d %H:%M} UTC.\n"
            "Las posiciones abiertas se siguen gestionando."
        )

    def paused_heads(self) -> dict[str, str]:
        """Cabezas que ahora mismo no pueden abrir posiciones, con el motivo."""
        from .pause_control import describe_until, manual_key
        out: dict[str, str] = {}
        if not self.enforce_pause_rules:
            return out
        now = self._now().timestamp()
        seen: set[str] = set()
        for ins in self.config.instruments:
            if ins.category in seen:
                continue
            seen.add(ins.category)
            blockers = [h for h in ins.paused_while_open if any(p.category == h for p in self.positions)]
            if blockers:
                out[ins.category] = f"mientras {', '.join(blockers)} tenga posiciones"
            until = self.storage.get_state(f"pause_until:{ins.category}") or 0.0
            if ins.strike_limit > 0 and now < until:
                limit = datetime.fromtimestamp(until, tz=timezone.utc)
                out[ins.category] = f"por strikes hasta {limit.isoformat(timespec='minutes')}"
            manual = self.storage.get_state(manual_key(ins.category)) or 0.0
            if now < manual:
                out[ins.category] = f"manual {describe_until(manual)}"
        return out

    def emergency_close_all(self, reason: str = "emergency_close") -> None:
        """Cierra inmediatamente todas las posiciones abiertas en el exchange."""
        logger.critical("[ENGINE] Iniciando cierre de emergencia de todas las posiciones (%d posiciones)", len(self.positions))
        still_open = []
        for pos in list(self.positions):
            current_price = self.last_prices.get(pos.symbol, pos.entry_price)
            exit_side = Side.SELL if pos.side is Side.BUY else Side.BUY
            close_order = Order(pos.symbol, exit_side, pos.amount, current_price, reason=reason)
            
            success = self._close_position(pos, close_order)
            if not success:
                logger.error("[ENGINE] No se pudo cerrar la posición %s en el cierre de emergencia", pos.symbol)
                still_open.append(pos)
        self.positions = still_open

    def _execute_partial_close(self, pos: Position, close_order: Order) -> bool:
        import time
        fill = None
        last_err = None
        for attempt in range(1, 4):
            try:
                fill = self.execution.execute(close_order)
                break
            except Exception as e:
                last_err = e
                logger.warning("[%s] Intento %d/3 de toma parcial fallido (%s)", pos.symbol, attempt, e)
                if attempt < 3:
                    time.sleep(1.0)

        if fill is None:
            logger.error("[%s] No se pudo realizar cierre parcial tras 3 intentos (%s); reintentaré en el próximo ciclo", pos.symbol, last_err)
            self.notifier.notify_execution_error(
                action="toma parcial",
                symbol=pos.symbol,
                error=last_err,
                details="Reintentando automáticamente en el siguiente ciclo (60s).",
            )
            return False

        self.storage.record_fill(fill)

        closed_amount = fill.filled_amount
        proportion = closed_amount / pos.amount if pos.amount else 0.5
        entry_fee_partial = pos.entry_fee * proportion
        pos.entry_fee -= entry_fee_partial

        direction = 1 if pos.side is Side.BUY else -1
        gross = (fill.filled_price - pos.entry_price) * closed_amount * direction
        fee_total = entry_fee_partial + fill.fee
        pnl_abs = gross - fee_total
        cost_basis = pos.entry_price * closed_amount
        pnl_pct = (pnl_abs / cost_basis * 100) if cost_basis else 0.0

        trade = ClosedTrade(
            symbol=pos.symbol, category=pos.category, strategy_name=pos.strategy_name,
            side=pos.side, amount=closed_amount, entry_price=pos.entry_price,
            exit_price=fill.filled_price, fee_total=fee_total, pnl_abs=pnl_abs,
            pnl_pct=pnl_pct, exit_reason=close_order.reason, opened_at=pos.opened_at,
        )
        trade_id = self.storage.record_closed_trade(trade)
        self._track_unconfirmed("exit", fill, trade=trade, trade_id=trade_id)
        self.closed_trades.append(trade)

        # Ajustar la posición abierta existente (reducir cantidad y ajustar a Breakeven)
        pos.amount -= closed_amount
        pos.partial_tp_done = True
        if pos.side is Side.BUY:
            pos.stop_loss = max(pos.stop_loss, pos.entry_price)
        else:
            pos.stop_loss = min(pos.stop_loss, pos.entry_price)

        self._save_cash()
        head = f"{pos.category}/{pos.strategy_name}"
        quote = self.config.risk.quote_currency
        equity = self.equity()
        logger.info(
            "[%s] TOMA PARCIAL %s %s @ %.6f | P&L %.2f (%.2f%%) | SL Breakeven %.6f | saldo=%.2f %s",
            head, pos.symbol, pos.side.value, fill.filled_price, pnl_abs, pnl_pct, pos.stop_loss, equity, quote,
        )
        self._log_head(pos.category,
                       f"TOMA PARCIAL {pos.symbol} @ {fill.filled_price:.6f} | P&L {pnl_abs:+.2f} {quote} ({pnl_pct:+.2f}%) | SL Breakeven {pos.stop_loss:.6f}")
        self.notifier.notify_partial_tp(
            symbol=pos.symbol,
            fill_price=fill.filled_price,
            head=head,
            pnl_abs=pnl_abs,
            pnl_pct=pnl_pct,
            stop_loss=pos.stop_loss,
            equity=equity,
            quote=quote,
        )
        return True

    def _close_position(self, pos: Position, close_order) -> bool:
        import time
        executed = self._stop_already_executed(pos)
        if executed:
            return True                               # la vendió antes el stop del exchange
        if executed is None:
            return False                              # estado dudoso: se reintenta en el siguiente sondeo
        fill = None
        last_err = None
        for attempt in range(1, 4):
            try:
                fill = self.execution.execute(close_order)
                break
            except Exception as e:
                last_err = e
                logger.warning("[%s] Intento %d/3 de cierre (%s) fallido (%s)", pos.symbol, attempt, close_order.reason, e)
                if attempt < 3:
                    time.sleep(1.0)

        if fill is None:
            logger.error("[%s] No se pudo cerrar posición tras 3 intentos (%s); reintentaré en el próximo ciclo", pos.symbol, last_err)
            self.notifier.notify_execution_error(
                action="cerrar posición",
                symbol=pos.symbol,
                error=last_err,
                details=f"Motivo salida: <b>{close_order.reason}</b>\n⚠️ La posición permanece abierta y se reintentará en el próximo ciclo (60s).",
            )
            return False

        self._record_close(pos, fill, close_order.reason)
        return True

    def _record_close(self, pos: Position, fill, reason: str, note: str = "") -> None:
        """Contabiliza el cierre completo de `pos` con la ejecución `fill`."""
        self.storage.record_fill(fill)

        direction = 1 if pos.side is Side.BUY else -1
        gross = (fill.filled_price - pos.entry_price) * pos.amount * direction
        fee_total = pos.entry_fee + fill.fee
        pnl_abs = gross - fee_total
        cost_basis = pos.entry_price * pos.amount
        pnl_pct = (pnl_abs / cost_basis * 100) if cost_basis else 0.0

        trade = ClosedTrade(
            symbol=pos.symbol, category=pos.category, strategy_name=pos.strategy_name,
            side=pos.side, amount=pos.amount, entry_price=pos.entry_price,
            exit_price=fill.filled_price, fee_total=fee_total, pnl_abs=pnl_abs,
            pnl_pct=pnl_pct, exit_reason=reason, opened_at=pos.opened_at,
            # En los cierres por stop se guarda el nivel, para medir el deslizamiento real.
            stop_price=pos.stop_loss if reason in STRIKE_EXIT_REASONS else None,
        )
        if trade.stop_slippage_pct is not None:
            logger.info(
                "[%s] stop de %s: nivel %.6f, venta %.6f (%+.2f%% respecto al nivel)",
                pos.category, pos.symbol, trade.stop_price, trade.exit_price, trade.stop_slippage_pct,
            )
        trade_id = self.storage.record_closed_trade(trade)
        self._track_unconfirmed("exit", fill, trade=trade, trade_id=trade_id)
        self.storage.delete_open_position(pos)   # ya no está abierta
        self._register_strike(trade)
        self._save_cash()
        self.closed_trades.append(trade)
        head = f"{pos.category}/{pos.strategy_name}"
        quote = self.config.risk.quote_currency
        equity = self.equity(exclude=pos)   # ya realizada: no contar su no-realizado
        label = f"{reason}, {note}" if note else reason
        logger.info(
            "[%s] CIERRA %s %s @ %.6f (%s) | P&L %.2f (%.2f%%) | saldo=%.2f %s",
            head, pos.symbol, pos.side.value, fill.filled_price, label,
            pnl_abs, pnl_pct, equity, quote,
        )
        self._log_head(pos.category,
                       f"CIERRA {pos.symbol} ({label}) P&L {pnl_abs:+.2f} ({pnl_pct:+.2f}%) | saldo {equity:.2f} {quote}")
        self.notifier.notify_trade_closed(
            symbol=pos.symbol,
            entry_price=pos.entry_price,
            exit_price=fill.filled_price,
            reason=label,
            pnl_abs=pnl_abs,
            pnl_pct=pnl_pct,
            head=head,
            equity=equity,
            quote=quote,
        )

    # --- Stops de emergencia en el exchange (ver exchange_stops.py) ---------------------

    def _sync_stop(self, pos: Position) -> None:
        """Crea o repone la orden de stop del exchange de la posición, si procede."""
        if self.stop_guard.enabled and self.stop_guard.sync(pos):
            self.storage.update_stop_order(pos)
            self.storage.set_state("exchange_stops_used", 1.0)   # hay órdenes que limpiar si se desactiva

    def _stop_already_executed(self, pos: Position) -> bool | None:
        """Retira la orden de stop del exchange antes de que el bot venda. Devuelve:
          False -> el bot puede vender;
          True  -> la orden ya se había ejecutado (el activo no está): cierre registrado;
          None  -> no se sabe (la orden no está y no se pudo leer el saldo): reintentar luego."""
        guard = self.stop_guard
        if not guard.enabled or not pos.stop_order_id:
            return False
        status = guard.release(pos)
        if status == "cancelled":
            self.storage.update_stop_order(pos)
            guard.wait_until_free(pos)                # en OKX la moneda estaba bloqueada por la orden
            return False
        gone = guard.position_gone(pos)
        if gone:
            self._finish_exchange_stop(pos)           # el activo no está: lo vendió el exchange
            return True
        if status == "error":
            if guard.locks_balance:
                # La orden sigue viva y tiene la moneda bloqueada: el bot no puede venderla.
                # Se reintenta en el siguiente sondeo; mientras, esa orden sigue protegiendo.
                logger.warning("[%s] No vendo todavía: la orden de stop %s sigue viva y bloquea la moneda; "
                               "reintento en el siguiente sondeo", pos.symbol, pos.stop_order_id)
                return None
            # No se pudo cancelar: vender es lo prioritario. Si la orden sigue viva, se
            # cancelará como huérfana en el siguiente ciclo (el exchange no bloquea el saldo).
            return False
        if gone is None:
            return None
        # La orden ya no existe pero el activo sigue ahí: el bot vende con normalidad.
        pos.stop_order_id, pos.stop_order_price, pos.stop_order_amount = "", 0.0, 0.0
        self.storage.update_stop_order(pos)
        return False

    def _finish_exchange_stop(self, pos: Position) -> None:
        """Registra el cierre de una posición que vendió la orden de stop del exchange."""
        from .models import Fill
        reason = "trailing-stop" if (pos.trailing_stop_pct > 0 or pos.use_atr_trailing) else "stop-loss"
        order = Order(pos.symbol, Side.SELL, pos.amount, pos.stop_order_price or pos.stop_loss, reason=reason)
        fill = Fill(order=order, filled_price=order.price, filled_amount=pos.amount, fee=0.0,
                    order_id=pos.stop_order_id or None, confirmed=False)
        try:
            real = self.execution.confirm_fill(fill)
        except Exception as exc:
            logger.debug("No pude leer la ejecución de la orden de stop %s (%s)", pos.stop_order_id, exc)
            real = None
        logger.warning(
            "[%s] El stop de emergencia del exchange vendió %s (orden %s)%s",
            pos.category, pos.symbol, pos.stop_order_id,
            "" if real is not None else "; registro el precio de disparo y lo corrijo cuando el exchange lo confirme",
        )
        self._record_close(pos, real or fill, reason, note="stop del exchange")

    def sync_exchange_stops(self) -> None:
        """Una vez por ciclo y al arrancar: detecta las posiciones que vendió el exchange,
        cancela las órdenes que hayan quedado sin posición y repone las que falten."""
        guard = self.stop_guard
        if not guard.enabled:
            return
        self._alert_unprotected()                     # antes del listado: si el exchange falla, que avise igual
        open_orders = guard.open_orders()
        if open_orders is None:
            return                                    # sin listado fiable no se toca nada
        still: list[Position] = []
        for pos in self.positions:
            if pos.stop_order_id and pos.stop_order_id not in open_orders and not guard.is_recent(pos.stop_order_id):
                gone = guard.position_gone(pos)
                if gone:
                    self._finish_exchange_stop(pos)
                    continue
                if gone is False:                     # la orden desapareció y el activo sigue: se repone
                    logger.warning("[%s] La orden de stop %s ya no está en el exchange; la repongo", pos.symbol, pos.stop_order_id)
                    pos.stop_order_id, pos.stop_order_price, pos.stop_order_amount = "", 0.0, 0.0
                    self.storage.update_stop_order(pos)
            still.append(pos)
        self.positions = still
        _, failed = guard.cancel_orphans(self.positions, open_orders)
        if failed:
            # Una orden viva sin posición puede vender una compra posterior de esa moneda.
            logger.error("No pude cancelar órdenes de stop sin posición: %s", ", ".join(failed))
            now = self._now().timestamp()
            if now - self._orphan_alert_at > 3600:
                self._orphan_alert_at = now
                self.notifier.notify(
                    "🆘 <b>Órdenes de stop sin posición que no puedo cancelar</b>\n"
                    + "\n".join(failed)
                    + f"\nCancélalas a mano en {self.config.exchange_name}: podrían vender una compra posterior de esa moneda."
                )
        for pos in self.positions:
            self._sync_stop(pos)

    def _alert_unprotected(self) -> None:
        """Avisa (como mucho una vez por hora) si el exchange lleva un rato rechazando la
        orden de emergencia de alguna posición: mientras dure, solo la protege el stop del bot."""
        pending = self.stop_guard.unprotected(self.positions, UNPROTECTED_ALERT_SECONDS)
        if not pending:
            return
        now = self._now().timestamp()
        if now - self._unprotected_alert_at <= 3600:
            return
        self._unprotected_alert_at = now
        lines = [f"{symbol}: {seconds / 60:.0f} min ({error[:120]})" for symbol, seconds, error in pending]
        logger.error("Posiciones sin stop de emergencia en el exchange: %s", "; ".join(lines))
        self.notifier.notify(
            "⚠️ <b>Posiciones sin stop de emergencia en el exchange</b>\n"
            + "\n".join(lines)
            + "\nEl exchange rechaza crear la orden; el bot lo reintenta cada 5 min. "
            "Mientras tanto solo las protege el stop del bot: si el bot o el servidor se caen, quedan sin stop."
        )

    def release_exchange_stops(self) -> int:
        """Con la opción desactivada: retira las órdenes de stop que hubiera dejado el bot."""
        guard = self.stop_guard
        if guard.enabled or self.config.mode != "live" or self.exchange is None:
            return 0
        if not self.storage.get_state("exchange_stops_used") and not any(p.stop_order_id for p in self.positions):
            return 0                                  # nunca se usaron: no se consulta al exchange
        n = guard.cancel_all(self.positions)
        self.storage.set_state("exchange_stops_used", 0.0)
        for pos in self.positions:
            if pos.stop_order_id:
                pos.stop_order_id, pos.stop_order_price, pos.stop_order_amount = "", 0.0, 0.0
                self.storage.update_stop_order(pos)
        return n

    # --- Ejecuciones sin confirmar ----------------------------------------------------

    MAX_FILL_CONFIRM_ATTEMPTS = 30   # ciclos que se insiste antes de dejar los datos estimados

    def _track_unconfirmed(self, kind: str, fill, position: Position | None = None,
                           trade: ClosedTrade | None = None, trade_id: int = 0) -> None:
        """Apunta una ejecución que el exchange no confirmó a tiempo (precio, cantidad y
        comisión estimados) para corregirla en `reconcile_fills`."""
        if getattr(fill, "confirmed", True) is not False or not getattr(fill, "order_id", None):
            return
        self._unconfirmed.append({"kind": kind, "fill": fill, "position": position,
                                  "trade": trade, "trade_id": trade_id, "attempts": 0})

    def reconcile_fills(self) -> int:
        """Vuelve a consultar las ejecuciones apuntadas como estimadas y corrige la
        posición (compras) o la operación cerrada (ventas) con los datos reales.
        Devuelve cuántas corrigió. Se llama una vez por ciclo: nunca retrasa una venta."""
        if not self._unconfirmed:
            return 0
        fixed, pending = 0, []
        for item in self._unconfirmed:
            fill = item["fill"]
            try:
                real = self.execution.confirm_fill(fill)
            except Exception as exc:
                logger.debug("No pude confirmar la orden %s (%s)", fill.order_id, exc)
                real = None
            if real is None:
                item["attempts"] += 1
                if item["attempts"] >= self.MAX_FILL_CONFIRM_ATTEMPTS:
                    logger.warning(
                        "[%s] La orden %s sigue sin confirmar tras %d intentos: su registro se queda "
                        "con los datos estimados", fill.order.symbol, fill.order_id, item["attempts"],
                    )
                else:
                    pending.append(item)
                continue
            if item["kind"] == "entry":
                self._apply_confirmed_entry(item["position"], fill, real)
            else:
                self._apply_confirmed_exit(item["trade"], item["trade_id"], fill, real)
            fixed += 1
        self._unconfirmed = pending
        return fixed

    def _apply_confirmed_entry(self, pos: Position, estimated, real) -> None:
        if not any(p is pos for p in self.positions):
            logger.warning(
                "[%s] La compra (orden %s) se confirmó con la posición ya cerrada: su operación "
                "queda con la entrada estimada", pos.symbol, real.order_id,
            )
            return
        before = (pos.entry_price, pos.amount, pos.entry_fee)
        # Por diferencias: si ya hubo una toma parcial, se conserva lo vendido.
        pos.amount = max(pos.amount + real.filled_amount - estimated.filled_amount, 0.0)
        pos.entry_fee = max(pos.entry_fee + real.fee - estimated.fee, 0.0)
        pos.entry_price = real.filled_price
        # Stop y objetivo se dejan donde estaban: se fijaron con el precio de la señal.
        self.storage.update_open_position_entry(pos)
        self._sync_stop(pos)                         # la cantidad real puede diferir de la estimada
        logger.info(
            "[%s] Compra confirmada (orden %s): precio %.6f -> %.6f, cantidad %.8f -> %.8f, comisión %.4f -> %.4f",
            pos.symbol, real.order_id, before[0], pos.entry_price, before[1], pos.amount, before[2], pos.entry_fee,
        )

    def _apply_confirmed_exit(self, trade: ClosedTrade, trade_id: int, estimated, real) -> None:
        before = (trade.exit_price, trade.pnl_abs)
        direction = 1 if trade.side is Side.BUY else -1
        entry_fee = trade.fee_total - estimated.fee
        trade.exit_price = real.filled_price
        trade.fee_total = entry_fee + real.fee
        trade.pnl_abs = (real.filled_price - trade.entry_price) * trade.amount * direction - trade.fee_total
        cost_basis = trade.entry_price * trade.amount
        trade.pnl_pct = (trade.pnl_abs / cost_basis * 100) if cost_basis else 0.0
        self.storage.update_closed_trade(trade_id, trade)
        quote = self.config.risk.quote_currency
        logger.info(
            "[%s] Venta confirmada (orden %s, %s): precio %.6f -> %.6f, P&L %.2f -> %.2f %s",
            trade.symbol, real.order_id, trade.exit_reason, before[0], trade.exit_price,
            before[1], trade.pnl_abs, quote,
        )
        self._log_head(trade.category,
                       f"CORRIGE {trade.symbol} ({trade.exit_reason}) venta real {trade.exit_price:.6f} | "
                       f"P&L {trade.pnl_abs:+.2f} ({trade.pnl_pct:+.2f}%)")
        self.notifier.notify(
            f"ℹ️ <b>Corrección</b> {trade.symbol} ({trade.exit_reason})\n"
            f"El exchange confirmó la venta: {before[0]:.6f} → {trade.exit_price:.6f}\n"
            f"P&L: {before[1]:+.2f} → <b>{trade.pnl_abs:+.2f} {quote}</b> ({trade.pnl_pct:+.2f}%)"
        )

    def _log_head(self, category: str, text: str) -> None:
        """Escribe una línea en el log específico de la cabeza (logs/heads/<cat>.log)."""
        if not category or not self.head_log_dir:
            return
        try:
            from datetime import datetime, timezone
            from pathlib import Path
            path = Path(self.head_log_dir) / f"{category}.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now(timezone.utc).isoformat()} | {text}\n")
        except Exception:
            logger.debug("No pude escribir el log de la cabeza %s", category)

    # --- Persistencia / readopción de posiciones -----------------------------------

    def _save_cash(self) -> None:
        """Guarda el efectivo SIMULADO (solo paper; en live el saldo es real y no
        hace falta persistirlo — evita un fetch de balance por cada operación)."""
        if not hasattr(self.execution, "set_balance"):
            return
        try:
            self.storage.set_state("paper_balance", self.execution.get_balance())
        except Exception:
            logger.debug("No pude persistir el efectivo simulado")

    def load_positions(self) -> int:
        """Readopta las posiciones abiertas persistidas para seguir gestionándolas
        tras un reinicio (clave en live: si no, quedarían huérfanas). En paper
        restaura también el efectivo simulado para que el equity cuadre. En live
        RECONCILIA contra el saldo real del exchange (descarta/ajusta lo que no cuadre)."""
        self.positions = self.storage.load_open_positions()
        if self.config.mode == "live":
            # Posiciones en otra moneda de cotización son de otro exchange (cambio de
            # KuCoin a Bybit a medias): reconciliarlas contra esta cuenta las daría por
            # vendidas y anotaría cierres falsos. Mejor no arrancar.
            quote = self.config.risk.quote_currency
            foreign = [p.symbol for p in self.positions if p.symbol.split(":")[0].split("/")[-1] != quote]
            if foreign:
                self.positions = []
                raise ForeignPositionsError(
                    f"Hay posiciones abiertas que no cotizan en {quote} ({', '.join(foreign)}): son de otro "
                    f"exchange. Ciérralas allí con la configuración anterior antes de arrancar en {self.config.exchange_name}."
                )
        for pos in self.positions:
            try:
                ins = self.config.instrument(pos.symbol)
                if pos.partial_tp_pct == 0.0 and getattr(ins, "partial_take_profit_pct", 0.0) > 0:
                    pos.partial_tp_pct = ins.partial_take_profit_pct
                    pos.partial_tp_ratio = ins.partial_take_profit_ratio
            except KeyError:
                pass

        setter = getattr(self.execution, "set_balance", None)   # solo el motor paper
        cash = self.storage.get_state("paper_balance")
        if callable(setter) and cash is not None:
            setter(cash)

        if self.config.mode == "live" and self.exchange is not None and self.positions:
            self._reconcile_live()

        self._seed_last_prices()

        if self.positions:
            logger.info(
                "Readoptadas %d posiciones abiertas persistidas: %s",
                len(self.positions),
                ", ".join(f"{p.category}/{p.symbol}" for p in self.positions),
            )
        return len(self.positions)

    def _seed_last_prices(self) -> None:
        """Pide el precio de mercado de las posiciones readoptadas. Sin esto, hasta el
        primer ciclo el equity las valora a su precio de entrada (mensaje de arranque,
        primer status publicado y base del cortafuegos diario)."""
        fetch = getattr(self.exchange, "fetch_last_prices", None)
        if not self.positions or not callable(fetch):
            return
        try:
            prices = fetch(list(dict.fromkeys(p.symbol for p in self.positions)))
        except Exception as exc:
            logger.warning("No pude leer los precios de las posiciones readoptadas (%s)", exc)
            return
        if isinstance(prices, dict):
            self.last_prices.update({s: float(p) for s, p in prices.items() if p and p > 0})

    # Tolerancias de reconciliación (relativas al importe registrado).
    RECONCILE_GONE_RATIO = 0.05    # saldo real < 5% del registrado -> la posición ya no existe
    RECONCILE_SHRINK_RATIO = 0.95  # saldo real < 95% -> ajustar a lo que de verdad hay

    def _reconcile_live(self) -> None:
        """Compara cada posición readoptada con el saldo REAL del activo base en la
        cuenta. Si el activo ya no está (vendido a mano, nunca se llenó…) la descarta;
        si hay menos de lo registrado, la ajusta; avisa de cada descuadre."""
        try:
            balances = self.exchange.fetch_balances_total()
        except Exception:
            logger.exception("Reconciliación: no pude leer los saldos reales; readopto sin reconciliar")
            return

        kept: list[Position] = []
        for pos in self.positions:
            base = pos.symbol.split("/")[0]
            real = balances.get(base, 0.0)
            if pos.amount <= 0:
                continue
            ratio = real / pos.amount

            if ratio < self.RECONCILE_GONE_RATIO and pos.stop_order_id and self.stop_guard.enabled:
                self._finish_exchange_stop(pos)       # la vendió el stop de emergencia con el bot parado
                continue

            if ratio < self.RECONCILE_GONE_RATIO:
                logger.warning(
                    "Reconciliación: %s registrada con %.8f %s pero en la cuenta hay %.8f "
                    "-> DESCARTADA (vendida a mano o nunca llenó)", pos.symbol, pos.amount, base, real)
                self.storage.delete_open_position(pos)
                self.notifier.notify(
                    f"⚠️ <b>Reconciliación</b> {pos.symbol}: no hay saldo ({real:.8f} {base}); "
                    f"posición descartada (no la gestiono).")
                continue

            if ratio < self.RECONCILE_SHRINK_RATIO:
                logger.warning(
                    "Reconciliación: %s registrada %.8f %s, real %.8f -> AJUSTO a %.8f",
                    pos.symbol, pos.amount, base, real, real)
                self.notifier.notify(
                    f"⚠️ <b>Reconciliación</b> {pos.symbol}: ajusto tamaño "
                    f"{pos.amount:.8f} → {real:.8f} {base} (saldo real menor).")
                pos.amount = real
                self.storage.update_open_position(pos)

            kept.append(pos)

        self.positions = kept

    # --- Cartera -------------------------------------------------------------------

    def equity(self, exclude: Position | None = None) -> float:
        """Valor total de la cuenta = efectivo + valor de mercado de las posiciones.

        El efectivo (get_balance) ya tiene descontado el importe al comprar, así que
        hay que sumar el VALOR actual de lo que se tiene (no solo el P&L). Para
        largos suma +precio*cantidad; para cortos resta (coste de recompra)."""
        total = self.execution.get_balance()
        for p in self.positions:
            if p is exclude:
                continue
            value = self.last_prices.get(p.symbol, p.entry_price) * p.amount
            total += value if p.side is Side.BUY else -value

        # Si el Carry Trade tiene posiciones abiertas en spot, sumar su valor de mercado
        carry_runner = getattr(self, "carry_runner", None)
        if carry_runner is not None and getattr(carry_runner, "mgr", None) is not None:
            for cp in carry_runner.mgr.positions.values():
                spot_amt = getattr(cp, "spot_amount", 0.0)
                if spot_amt > 0:
                    val = self.last_prices.get(cp.symbol, getattr(cp, "spot_entry", 0.0)) * spot_amt
                    total += val

        return total

    # --- Bucle principal (live / paper continuo) -----------------------------------

    def run(self) -> None:
        import time

        cfg, m = self.config, self.config
        interval = cfg.engine.poll_interval_seconds
        symbols = cfg.symbols()
        logger.info(
            "Bot iniciado en modo %s | %d símbolos | %s | cada %ds",
            cfg.mode.upper(), len(symbols), cfg.timeframe, interval,
        )
        try:
            while True:
                if self.risk.halted:
                    logger.warning("Bot detenido por gestión de riesgo. Saliendo.")
                    break
                for symbol in symbols:
                    try:
                        candles = self.exchange.fetch_ohlcv(
                            symbol, cfg.timeframe, cfg.lookback
                        )
                        self.process(symbol, candles)
                    except Exception:
                        logger.exception("[%s] error en el ciclo; continúo", symbol)
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Interrumpido por el usuario. Cerrando.")
        finally:
            self.storage.close()
