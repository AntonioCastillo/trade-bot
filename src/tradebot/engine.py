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

from .config import Config
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

        self._check_exits(symbol, current_price)
        self._check_entry(symbol, candles, current_price)

        if self.enforce_daily_loss:
            self.risk.register_equity(self.equity())

    def _check_exits(self, symbol: str, current_price: float) -> None:
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
                still_open.append(pos)
                continue
            # 2) Salida por TP / SL / trailing.
            decision = self.risk.evaluate_exit(pos, current_price)
            if decision.order is not None and self._close_position(pos, decision.order):
                continue  # cerrada con éxito -> no se mantiene
            still_open.append(pos)
        self.positions = still_open

    def _check_entry(self, symbol: str, candles: pd.DataFrame, current_price: float) -> None:
        strategy = self.strategies[symbol]
        signal = strategy.generate_signal(symbol, candles)
        if signal.type is SignalType.HOLD:
            return

        instrument = self.config.instrument(symbol)
        head = f"{instrument.category}/{instrument.strategy_name}"

        # Filtro de régimen: la cabeza solo entra si el mercado le favorece.
        if instrument.regimes:
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
