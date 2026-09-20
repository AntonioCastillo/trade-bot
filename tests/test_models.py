from datetime import datetime, timezone

from tradebot.models import (
    CarryPosition,
    ClosedTrade,
    Fill,
    Order,
    Position,
    Side,
    Signal,
    SignalType,
)


def test_signal_to_from_dict():
    sig = Signal(SignalType.BUY, "BTC/USDT", 60000.0, reason="test signal")
    d = sig.to_dict()
    assert d["type"] == "buy"
    assert d["symbol"] == "BTC/USDT"
    assert d["price"] == 60000.0
    assert d["reason"] == "test signal"

    restored = Signal.from_dict(d)
    assert restored.type is SignalType.BUY
    assert restored.symbol == "BTC/USDT"
    assert restored.price == 60000.0
    assert restored.reason == "test signal"


def test_order_and_fill_to_from_dict():
    order = Order("ETH/USDT", Side.BUY, 1.5, 2500.0, reason="test order")
    d_order = order.to_dict()
    assert d_order["side"] == "buy"
    assert d_order["amount"] == 1.5

    restored_order = Order.from_dict(d_order)
    assert restored_order.side is Side.BUY
    assert restored_order.amount == 1.5

    fill = Fill(order=order, filled_price=2501.0, filled_amount=1.5, fee=0.5)
    d_fill = fill.to_dict()
    assert d_fill["filled_price"] == 2501.0
    assert d_fill["fee"] == 0.5

    restored_fill = Fill.from_dict(d_fill)
    assert restored_fill.order.symbol == "ETH/USDT"
    assert restored_fill.filled_price == 2501.0


def test_position_to_from_dict():
    pos = Position(
        symbol="SOL/USDT",
        side=Side.BUY,
        amount=10.0,
        entry_price=120.0,
        stop_loss=115.0,
        take_profit=130.0,
        category="altcoins",
        strategy_name="trend",
        entry_fee=0.2,
        reason="breakout",
        trailing_stop_pct=0.03,
        peak_price=125.0,
        bars_held=5,
        partial_tp_pct=0.05,
        partial_tp_ratio=0.5,
        partial_tp_done=True,
        use_atr_trailing=True,
        atr_trailing_mult=2.5,
        db_id=42,
    )
    d = pos.to_dict()
    assert d["symbol"] == "SOL/USDT"
    assert d["db_id"] == 42
    assert d["partial_tp_done"] is True

    restored = Position.from_dict(d)
    assert restored.symbol == "SOL/USDT"
    assert restored.side is Side.BUY
    assert restored.amount == 10.0
    assert restored.db_id == 42
    assert restored.partial_tp_done is True
    assert restored.use_atr_trailing is True
    assert restored.unrealized_pnl(125.0) == 50.0


def test_closed_trade_to_from_dict():
    dt_open = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    dt_close = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    trade = ClosedTrade(
        symbol="BTC/USDT",
        category="majors",
        strategy_name="breakout",
        side=Side.BUY,
        amount=0.5,
        entry_price=50000.0,
        exit_price=52000.0,
        fee_total=1.5,
        pnl_abs=998.5,
        pnl_pct=3.994,
        exit_reason="take-profit",
        opened_at=dt_open,
        closed_at=dt_close,
    )
    d = trade.to_dict()
    assert d["is_win"] is True
    assert d["duration_seconds"] == 7200.0

    restored = ClosedTrade.from_dict(d)
    assert restored.symbol == "BTC/USDT"
    assert restored.is_win is True
    assert restored.duration_seconds == 7200.0
    assert restored.pnl_abs == 998.5


def test_carry_position_to_from_dict():
    cp = CarryPosition(
        symbol="ETH/USDT",
        notional=100.0,
        spot_entry=2000.0,
        perp_entry=2000.0,
        spot_amount=0.05,
        perp_amount=0.05,
        funding_collected=0.15,
        last_funding_ts=1700000000,
    )
    assert cp.spot_value(2100.0) == 105.0
    assert cp.perp_pnl(2100.0) == -5.0
    assert cp.net_pnl(2100.0, 2100.0) == 0.15

    d = cp.to_dict()
    assert d["symbol"] == "ETH/USDT"
    assert d["funding_collected"] == 0.15

    restored = CarryPosition.from_dict(d)
    assert restored.symbol == "ETH/USDT"
    assert restored.funding_collected == 0.15
    assert restored.spot_amount == 0.05
