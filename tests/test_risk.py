import pytest
from conftest import make_instrument

from tradebot.config import RiskConfig
from tradebot.models import Side, Signal, SignalType
from tradebot.risk import RiskManager


def _risk(**overrides) -> RiskManager:
    cfg = RiskConfig(
        starting_balance=10_000,
        position_size_pct=0.10,
        max_open_positions=1,
        stop_loss_pct=0.03,
        take_profit_pct=0.06,
        max_daily_loss_pct=0.05,
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return RiskManager(cfg)


def test_entry_sizes_position_by_instrument_pct():
    rm = _risk()
    ins = make_instrument(position_size_pct=0.10)
    sig = Signal(SignalType.BUY, "BTC/USDT", price=100.0)
    decision = rm.evaluate_entry(sig, ins, balance=10_000, open_positions=[])
    assert decision.order is not None
    # 10% de 10.000 = 1.000 USDT / 100 = 10 unidades.
    assert decision.order.amount == 10.0
    assert decision.order.side is Side.BUY


def test_entry_rejected_when_max_positions_reached():
    rm = _risk()
    ins = make_instrument()
    sig = Signal(SignalType.BUY, "BTC/USDT", price=100.0)
    other = make_instrument(symbol="ETH/USDT")
    pos = rm.build_position(other, Side.BUY, 1, 100, entry_fee=0.1, reason="x")
    decision = rm.evaluate_entry(sig, ins, balance=10_000, open_positions=[pos])
    assert decision.order is None


def test_no_duplicate_position_same_symbol():
    rm = _risk(max_open_positions=5)
    ins = make_instrument()
    sig = Signal(SignalType.BUY, "BTC/USDT", price=100.0)
    pos = rm.build_position(ins, Side.BUY, 1, 100, entry_fee=0.1, reason="x")
    decision = rm.evaluate_entry(sig, ins, balance=10_000, open_positions=[pos])
    assert decision.order is None


def test_hold_signal_produces_no_order():
    rm = _risk()
    ins = make_instrument()
    sig = Signal(SignalType.HOLD, "BTC/USDT", price=100.0)
    assert rm.evaluate_entry(sig, ins, 10_000, []).order is None


def test_stop_loss_triggers_exit():
    rm = _risk()
    ins = make_instrument()
    pos = rm.build_position(ins, Side.BUY, 1, entry_price=100.0, entry_fee=0.1, reason="x")
    decision = rm.evaluate_exit(pos, current_price=96.0)  # SL al 3% -> 97
    assert decision.order is not None
    assert decision.order.side is Side.SELL
    assert "stop-loss" in decision.reason


def test_take_profit_triggers_exit():
    rm = _risk()
    ins = make_instrument()
    pos = rm.build_position(ins, Side.BUY, 1, entry_price=100.0, entry_fee=0.1, reason="x")
    decision = rm.evaluate_exit(pos, current_price=107.0)  # TP al 6% -> 106
    assert decision.order is not None
    assert "take-profit" in decision.reason


def test_no_exit_within_range():
    rm = _risk()
    ins = make_instrument()
    pos = rm.build_position(ins, Side.BUY, 1, entry_price=100.0, entry_fee=0.1, reason="x")
    assert rm.evaluate_exit(pos, current_price=101.0).order is None


def test_per_category_sl_tp_override():
    rm = _risk()
    ins = make_instrument(stop_loss_pct=0.05, take_profit_pct=0.12)
    pos = rm.build_position(ins, Side.BUY, 1, entry_price=100.0, entry_fee=0.1, reason="x")
    assert pos.stop_loss == pytest.approx(95.0)
    assert pos.take_profit == pytest.approx(112.0)


def test_trailing_stop_ratchets_up_and_never_loosens():
    rm = _risk()
    ins = make_instrument(stop_loss_pct=0.10, trailing_stop_pct=0.05)
    pos = rm.build_position(ins, Side.BUY, 1, entry_price=100.0, entry_fee=0.1, reason="x")
    assert pos.stop_loss == pytest.approx(90.0)   # stop inicial: -10%

    # El precio sube a 120 -> el trailing sube el stop a 114 (120 * 0.95).
    rm.evaluate_exit(pos, current_price=120.0)
    assert pos.stop_loss == pytest.approx(114.0)

    # El precio baja a 118 -> el stop NO afloja (sigue en 114).
    rm.evaluate_exit(pos, current_price=118.0)
    assert pos.stop_loss == pytest.approx(114.0)


def test_trailing_stop_triggers_exit_with_trailing_reason():
    rm = _risk()
    ins = make_instrument(stop_loss_pct=0.10, trailing_stop_pct=0.05)
    pos = rm.build_position(ins, Side.BUY, 1, entry_price=100.0, entry_fee=0.1, reason="x")
    rm.evaluate_exit(pos, current_price=120.0)          # stop sube a 114
    decision = rm.evaluate_exit(pos, current_price=113.0)  # cae por debajo -> cierra
    assert decision.order is not None
    assert decision.reason.endswith("trailing-stop")


def test_daily_loss_halts_bot():
    rm = _risk()
    ins = make_instrument()
    rm.reset_day(10_000)
    rm.register_equity(9_400)  # -6% > límite 5%
    assert rm.halted is True
    sig = Signal(SignalType.BUY, "BTC/USDT", price=100.0)
    assert rm.evaluate_entry(sig, ins, 9_400, []).order is None
