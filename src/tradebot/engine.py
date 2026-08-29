"""Motor orquestador de cartera: une market data, estrategias (una por símbolo),
riesgo y ejecución, sobre un balance compartido.

- `process(symbol, candles)` = un ciclo de decisión para UN símbolo.
- `run()` recorre todos los instrumentos en bucle (modo live/paper continuo).

Cada cierre de posición se persiste como un `ClosedTrade` con su P&L, que es lo
que luego se consulta para juzgar la viabilidad.
"""

from __future__ import annotations

import logging

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
        self.positions: list[Position] = []
        self.last_prices: dict[str, float] = {}
        self.closed_trades: list[ClosedTrade] = []

    # --- Ciclo de decisión de un símbolo -------------------------------------------

    def process(self, symbol: str, candles: pd.DataFrame) -> None:
        current_price = float(candles["close"].iloc[-1])
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
                self.notifier.notify(
                    "🚨 <b>DISYUNTOR CRÍTICO ACTIVADO</b> 🚨\n"
                    f"El Drawdown global de la cuenta ha superado el límite permitido "
                    f"({self.risk.global_drawdown * 100:.1f}% >= {getattr(self.config.risk, 'max_account_drawdown_pct', 0.15) * 100:.1f}%).\n"
                    "Cerrando todas las posiciones abiertas y deteniendo bot de forma permanente."
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

    def _check_exits(self, symbol: str, current_price: float, candles: pd.DataFrame | None = None) -> None:
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
            decision = self.risk.evaluate_exit(pos, current_price, current_atr=current_atr)
            if decision.order is not None:
                if decision.order.reason == "partial-take-profit":
                    if self._execute_partial_close(pos, decision.order):
                        self.storage.update_open_position(pos)
                        still_open.append(pos)
                        continue
                elif self._close_position(pos, decision.order):
                    continue  # cerrada con éxito -> no se mantiene
            self.storage.update_open_position(pos)   # persistir trailing/bars_held/partial_tp
            still_open.append(pos)
        self.positions = still_open

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
                    use_atr_trailing=sample_ins.use_atr_trailing,
                    atr_trailing_mult=sample_ins.atr_trailing_mult,
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

        # Filtro Macro de BTC: congela nuevas compras en altcoins si BTC < EMA50
        if getattr(instrument, "macro_btc_filter", False):
            from .regime import is_btc_macro_bullish
            if not is_btc_macro_bullish(self.exchange):
                logger.info("[%s] Compras pausadas en %s (Filtro Macro BTC: BTC < EMA50)", head, symbol)
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

        balance = self.execution.get_balance()
        decision = self.risk.evaluate_entry(signal, instrument, balance, self.positions)
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
        )
        self.positions.append(position)
        self.storage.save_open_position(position)   # persistir para reinicios
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
        self.notifier.notify(
            f"🟢 <b>ABRE</b> {position.side.value.upper()} {symbol}\n"
            f"Cabeza: {head}\n"
            f"Precio: {position.entry_price:.6f}  |  Tamaño: {position.amount:.8f}\n"
            f"SL: {position.stop_loss:.6f}  TP: {position.take_profit:.6f}\n"
            f"Saldo cuenta: {equity:.2f} {quote}\n"
            f"Motivo: {signal.reason}"
        )

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
        try:
            fill = self.execution.execute(close_order)
        except OrderRejected as e:
            logger.warning("[%s] no se pudo realizar cierre parcial (%s)", pos.symbol, e)
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
        self.storage.record_closed_trade(trade)
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
        self.notifier.notify(
            f"💰 <b>TOMA PARCIAL (50%)</b> {pos.symbol}\n"
            f"Cabeza: {head}\n"
            f"Precio venta: {fill.filled_price:.6f}  |  P&L: {pnl_abs:+.2f} {quote} ({pnl_pct:+.2f}%)\n"
            f"SL restante ajustado a Breakeven: {pos.stop_loss:.6f}\n"
            f"Saldo cuenta: {equity:.2f} {quote}"
        )
        return True

    def _close_position(self, pos: Position, close_order) -> bool:
        try:
            fill = self.execution.execute(close_order)
        except OrderRejected as e:
            logger.warning("[%s] no se pudo cerrar (%s); reintentaré", pos.symbol, e)
            return False
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
            pnl_pct=pnl_pct, exit_reason=close_order.reason, opened_at=pos.opened_at,
        )
        self.storage.record_closed_trade(trade)
        self.storage.delete_open_position(pos)   # ya no está abierta
        self._save_cash()
        self.closed_trades.append(trade)
        head = f"{pos.category}/{pos.strategy_name}"
        quote = self.config.risk.quote_currency
        equity = self.equity(exclude=pos)   # ya realizada: no contar su no-realizado
        logger.info(
            "[%s] CIERRA %s %s @ %.6f (%s) | P&L %.2f (%.2f%%) | saldo=%.2f %s",
            head, pos.symbol, pos.side.value, fill.filled_price, close_order.reason,
            pnl_abs, pnl_pct, equity, quote,
        )
        self._log_head(pos.category,
                       f"CIERRA {pos.symbol} ({close_order.reason}) P&L {pnl_abs:+.2f} ({pnl_pct:+.2f}%) | saldo {equity:.2f} {quote}")
        emoji = "✅" if pnl_abs >= 0 else "❌"
        self.notifier.notify(
            f"{emoji} <b>CIERRA</b> {pos.symbol} ({close_order.reason})\n"
            f"Cabeza: {head}\n"
            f"Entrada: {pos.entry_price:.6f}  →  Salida: {fill.filled_price:.6f}\n"
            f"P&L: {pnl_abs:+.2f} {quote} ({pnl_pct:+.2f}%)\n"
            f"Saldo cuenta: {equity:.2f} {quote}"
        )
        return True

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
        RECONCILIA contra el saldo real de KuCoin (descarta/ajusta lo que no cuadre)."""
        self.positions = self.storage.load_open_positions()
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

        if self.positions:
            logger.info(
                "Readoptadas %d posiciones abiertas persistidas: %s",
                len(self.positions),
                ", ".join(f"{p.category}/{p.symbol}" for p in self.positions),
            )
        return len(self.positions)

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
