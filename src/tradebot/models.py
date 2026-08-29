"""Estructuras de datos compartidas entre las capas del bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class SignalType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Signal:
    """Lo que emite una estrategia. `reason` documenta el porqué (para logs/auditoría)."""

    type: SignalType
    symbol: str
    price: float
    reason: str = ""
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class Order:
    """Una orden ya aprobada por el risk manager, lista para ejecutarse."""

    symbol: str
    side: Side
    amount: float          # cantidad en moneda base (p.ej. BTC)
    price: float           # precio de referencia al crearla
    reason: str = ""
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class Fill:
    """Resultado de ejecutar una orden (real o simulada)."""

    order: Order
    filled_price: float
    filled_amount: float
    fee: float
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class Position:
    """Posición abierta. `entry_price` y `stop`/`take` marcan las salidas."""

    symbol: str
    side: Side
    amount: float
    entry_price: float
    stop_loss: float
    take_profit: float
    category: str = ""
    strategy_name: str = ""
    entry_fee: float = 0.0
    reason: str = ""
    trailing_stop_pct: float = 0.0   # 0 = desactivado
    peak_price: float = 0.0          # mejor precio alcanzado (para el trailing)
    bars_held: int = 0               # nº de velas que lleva abierta (salida por tiempo)
    partial_tp_pct: float = 0.0      # 0 = desactivado (p.ej. 0.05 para +5%)
    partial_tp_ratio: float = 0.5    # porcentaje de posición a cerrar en TP parcial (0.5 = 50%)
    partial_tp_done: bool = False    # True si ya se ha ejecutado el TP parcial
    opened_at: datetime = field(default_factory=_utcnow)
    db_id: int = 0                   # id de su fila en open_positions (0 = no persistida)

    def unrealized_pnl(self, current_price: float) -> float:
        direction = 1 if self.side is Side.BUY else -1
        return (current_price - self.entry_price) * self.amount * direction


@dataclass
class ClosedTrade:
    """Un round-trip completo (entrada + salida) con su P&L realizado.

    Es la unidad que persistimos para evaluar viabilidad y consultar por
    operación: precio de entrada/salida, beneficio/pérdida absoluto y %, etc.
    """

    symbol: str
    category: str
    strategy_name: str
    side: Side               # dirección de la posición (BUY = largo)
    amount: float
    entry_price: float
    exit_price: float
    fee_total: float
    pnl_abs: float           # P&L neto (ya descontadas comisiones)
    pnl_pct: float           # % sobre el capital invertido en la entrada
    exit_reason: str
    opened_at: datetime
    closed_at: datetime = field(default_factory=_utcnow)

    @property
    def duration_seconds(self) -> float:
        return (self.closed_at - self.opened_at).total_seconds()

    @property
    def is_win(self) -> bool:
        return self.pnl_abs > 0
