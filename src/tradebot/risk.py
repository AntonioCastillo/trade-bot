"""Gestión de riesgo. Traduce señales en órdenes dimensionadas y decide salidas.

Es la última línea de defensa: puede vetar cualquier señal. Cada instrumento
aporta su propio tamaño de posición y sus SL/TP (por categoría); los límites de
cartera (máximo de posiciones, pérdida diaria) son globales.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import Instrument, RiskConfig
from .models import Order, Position, Side, Signal, SignalType

logger = logging.getLogger(__name__)


@dataclass
class RiskDecision:
    order: Order | None
    reason: str


class RiskManager:
    def __init__(self, config: RiskConfig):
        self.config = config
        self._day_start_equity: float | None = None
        self._halted = False

    # --- Control de pérdida diaria -------------------------------------------------

    def register_equity(self, equity: float) -> None:
        if self._day_start_equity is None:
            self._day_start_equity = equity
            return
        drawdown = (self._day_start_equity - equity) / self._day_start_equity
        if drawdown >= self.config.max_daily_loss_pct and not self._halted:
            self._halted = True
            logger.error(
                "LIMITE DE PERDIDA DIARIA alcanzado (%.2f%%). Bot detenido.",
                drawdown * 100,
            )

    def reset_day(self, equity: float) -> None:
        self._day_start_equity = equity
        self._halted = False

    @property
    def halted(self) -> bool:
        return self._halted

    # --- Entradas ------------------------------------------------------------------

    def evaluate_entry(
        self,
        signal: Signal,
        instrument: Instrument,
        balance: float,
        open_positions: list[Position],
    ) -> RiskDecision:
        if self._halted:
            return RiskDecision(None, "bot detenido por límite de pérdida diaria")
        if signal.type is SignalType.HOLD:
            return RiskDecision(None, "señal HOLD")
        if len(open_positions) >= self.config.max_open_positions:
            return RiskDecision(None, "máximo de posiciones abiertas alcanzado")
        same_symbol = sum(1 for p in open_positions if p.symbol == signal.symbol)
        if same_symbol >= instrument.max_concurrent_per_symbol:
            return RiskDecision(
                None, f"ya hay {same_symbol} posición(es) en {signal.symbol}"
            )

        capital = balance * instrument.position_size_pct
        if capital <= 0 or signal.price <= 0:
            return RiskDecision(None, "capital o precio no válidos")

        amount = capital / signal.price
        side = Side.BUY if signal.type is SignalType.BUY else Side.SELL
        order = Order(
            symbol=signal.symbol,
            side=side,
            amount=amount,
            price=signal.price,
            reason=signal.reason,
        )
        return RiskDecision(order, f"entrada aprobada: {side.value} {amount:.8f}")

    def build_position(
        self,
        instrument: Instrument,
        side: Side,
        amount: float,
        entry_price: float,
        entry_fee: float,
        reason: str,
    ) -> Position:
        sl, tp = instrument.stop_loss_pct, instrument.take_profit_pct
        if side is Side.BUY:
            stop = entry_price * (1 - sl)
            take = entry_price * (1 + tp)
        else:
            stop = entry_price * (1 + sl)
            take = entry_price * (1 - tp)
        return Position(
            symbol=instrument.symbol,
            side=side,
            amount=amount,
            entry_price=entry_price,
            stop_loss=stop,
            take_profit=take,
            category=instrument.category,
            strategy_name=instrument.strategy_name,
            entry_fee=entry_fee,
            reason=reason,
            trailing_stop_pct=instrument.trailing_stop_pct,
            peak_price=entry_price,
        )

    # --- Salidas -------------------------------------------------------------------

    def evaluate_exit(self, position: Position, current_price: float) -> RiskDecision:
        close_side = Side.SELL if position.side is Side.BUY else Side.BUY

        self._update_trailing_stop(position, current_price)

        if position.side is Side.BUY:
            hit_stop = current_price <= position.stop_loss
            hit_take = current_price >= position.take_profit
        else:
            hit_stop = current_price >= position.stop_loss
            hit_take = current_price <= position.take_profit

        if hit_stop or hit_take:
            if hit_stop:
                reason = "trailing-stop" if position.trailing_stop_pct > 0 else "stop-loss"
            else:
                reason = "take-profit"
            order = Order(
                symbol=position.symbol,
                side=close_side,
                amount=position.amount,
                price=current_price,
                reason=reason,
            )
            return RiskDecision(order, f"cierre por {reason}")

        return RiskDecision(None, "posición dentro de rango")

    def _update_trailing_stop(self, position: Position, current_price: float) -> None:
        """Arrastra el stop siguiendo al mejor precio alcanzado. Solo lo mueve a
        favor: nunca afloja el stop una vez apretado."""
        if position.trailing_stop_pct <= 0:
            return
        pct = position.trailing_stop_pct
        if position.side is Side.BUY:
            position.peak_price = max(position.peak_price, current_price)
            trail = position.peak_price * (1 - pct)
            position.stop_loss = max(position.stop_loss, trail)
        else:
            position.peak_price = min(position.peak_price, current_price)
            trail = position.peak_price * (1 + pct)
            position.stop_loss = min(position.stop_loss, trail)
