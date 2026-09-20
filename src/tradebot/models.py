"""Estructuras de datos compartidas entre las capas del bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


from typing import Any


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class SignalType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(val: Any) -> datetime:
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            pass
    return _utcnow()


@dataclass(frozen=True)
class Signal:
    """Lo que emite una estrategia. `reason` documenta el porqué (para logs/auditoría)."""

    type: SignalType
    symbol: str
    price: float
    reason: str = ""
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "symbol": self.symbol,
            "price": self.price,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Signal:
        return cls(
            type=SignalType(d["type"]),
            symbol=d["symbol"],
            price=float(d["price"]),
            reason=d.get("reason", ""),
            timestamp=_parse_dt(d.get("timestamp")),
        )


@dataclass
class Order:
    """Una orden ya aprobada por el risk manager, lista para ejecutarse."""

    symbol: str
    side: Side
    amount: float          # cantidad en moneda base (p.ej. BTC)
    price: float           # precio de referencia al crearla
    reason: str = ""
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "amount": self.amount,
            "price": self.price,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Order:
        return cls(
            symbol=d["symbol"],
            side=Side(d["side"]),
            amount=float(d["amount"]),
            price=float(d["price"]),
            reason=d.get("reason", ""),
            timestamp=_parse_dt(d.get("timestamp")),
        )


@dataclass
class Fill:
    """Resultado de ejecutar una orden (real o simulada)."""

    order: Order
    filled_price: float
    filled_amount: float
    fee: float
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order.to_dict(),
            "filled_price": self.filled_price,
            "filled_amount": self.filled_amount,
            "fee": self.fee,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Fill:
        return cls(
            order=Order.from_dict(d["order"]),
            filled_price=float(d["filled_price"]),
            filled_amount=float(d["filled_amount"]),
            fee=float(d.get("fee", 0.0)),
            timestamp=_parse_dt(d.get("timestamp")),
        )


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
    use_atr_trailing: bool = False   # True para usar Trailing Stop Chandelier por ATR
    atr_trailing_mult: float = 3.0   # multiplicador ATR para Trailing Stop (p.ej. 3.0)
    opened_at: datetime = field(default_factory=_utcnow)
    db_id: int = 0                   # id de su fila en open_positions (0 = no persistida)

    def unrealized_pnl(self, current_price: float) -> float:
        direction = 1 if self.side is Side.BUY else -1
        return (current_price - self.entry_price) * self.amount * direction

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "amount": self.amount,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "category": self.category,
            "strategy_name": self.strategy_name,
            "entry_fee": self.entry_fee,
            "reason": self.reason,
            "trailing_stop_pct": self.trailing_stop_pct,
            "peak_price": self.peak_price,
            "bars_held": self.bars_held,
            "partial_tp_pct": self.partial_tp_pct,
            "partial_tp_ratio": self.partial_tp_ratio,
            "partial_tp_done": self.partial_tp_done,
            "use_atr_trailing": self.use_atr_trailing,
            "atr_trailing_mult": self.atr_trailing_mult,
            "opened_at": self.opened_at.isoformat(),
            "db_id": self.db_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Position:
        side_val = d["side"]
        side_enum = side_val if isinstance(side_val, Side) else Side(side_val)
        return cls(
            symbol=d["symbol"],
            side=side_enum,
            amount=float(d["amount"]),
            entry_price=float(d["entry_price"]),
            stop_loss=float(d["stop_loss"]),
            take_profit=float(d["take_profit"]),
            category=d.get("category", ""),
            strategy_name=d.get("strategy_name", ""),
            entry_fee=float(d.get("entry_fee", 0.0)),
            reason=d.get("reason", ""),
            trailing_stop_pct=float(d.get("trailing_stop_pct", 0.0)),
            peak_price=float(d.get("peak_price", 0.0)),
            bars_held=int(d.get("bars_held", 0)),
            partial_tp_pct=float(d.get("partial_tp_pct", 0.0)),
            partial_tp_ratio=float(d.get("partial_tp_ratio", 0.5)),
            partial_tp_done=bool(d.get("partial_tp_done", False)),
            use_atr_trailing=bool(d.get("use_atr_trailing", False)),
            atr_trailing_mult=float(d.get("atr_trailing_mult", 3.0)),
            opened_at=_parse_dt(d.get("opened_at")),
            db_id=int(d.get("db_id", 0)),
        )


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "category": self.category,
            "strategy_name": self.strategy_name,
            "side": self.side.value,
            "amount": self.amount,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "fee_total": self.fee_total,
            "pnl_abs": self.pnl_abs,
            "pnl_pct": self.pnl_pct,
            "exit_reason": self.exit_reason,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "is_win": self.is_win,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClosedTrade:
        side_val = d["side"]
        side_enum = side_val if isinstance(side_val, Side) else Side(side_val)
        return cls(
            symbol=d["symbol"],
            category=d.get("category", ""),
            strategy_name=d.get("strategy_name", ""),
            side=side_enum,
            amount=float(d["amount"]),
            entry_price=float(d["entry_price"]),
            exit_price=float(d["exit_price"]),
            fee_total=float(d.get("fee_total", 0.0)),
            pnl_abs=float(d["pnl_abs"]),
            pnl_pct=float(d["pnl_pct"]),
            exit_reason=d.get("exit_reason", ""),
            opened_at=_parse_dt(d.get("opened_at")),
            closed_at=_parse_dt(d.get("closed_at")),
        )


@dataclass
class CarryPosition:
    """Posición delta-neutral de funding rate (Spot largo + Perpetuo corto)."""

    symbol: str                 # spot, p.ej. ETH/USDT
    notional: float             # USDT por pata
    spot_entry: float
    perp_entry: float
    spot_amount: float
    perp_amount: float
    funding_collected: float = 0.0
    last_funding_ts: int = 0
    opened_at: datetime = field(default_factory=_utcnow)

    def spot_value(self, spot_now: float) -> float:
        return self.spot_amount * spot_now

    def perp_pnl(self, perp_now: float) -> float:
        # Corto: gana si el perp baja respecto a la entrada.
        return (self.perp_entry - perp_now) * self.perp_amount

    def net_pnl(self, spot_now: float, perp_now: float) -> float:
        """P&L neto (sin contar comisiones): (spot - notional) + perp corto + funding."""
        return (self.spot_value(spot_now) - self.notional) + self.perp_pnl(perp_now) + self.funding_collected

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "notional": self.notional,
            "spot_entry": self.spot_entry,
            "perp_entry": self.perp_entry,
            "spot_amount": self.spot_amount,
            "perp_amount": self.perp_amount,
            "funding_collected": self.funding_collected,
            "last_funding_ts": self.last_funding_ts,
            "opened_at": self.opened_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CarryPosition:
        return cls(
            symbol=d["symbol"],
            notional=float(d.get("notional", 0.0)),
            spot_entry=float(d.get("spot_entry", 0.0)),
            perp_entry=float(d.get("perp_entry", 0.0)),
            spot_amount=float(d.get("spot_amount", 0.0)),
            perp_amount=float(d.get("perp_amount", 0.0)),
            funding_collected=float(d.get("funding_collected", 0.0)),
            last_funding_ts=int(d.get("last_funding_ts", 0)),
            opened_at=_parse_dt(d.get("opened_at")),
        )
