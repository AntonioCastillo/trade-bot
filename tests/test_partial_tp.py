import pytest
import pandas as pd
from unittest.mock import MagicMock
from tradebot.config import Config, Instrument, RiskConfig
from tradebot.models import Order, Position, Side, Signal, SignalType
from tradebot.risk import RiskManager
from tradebot.engine import Engine
from tradebot.storage import Storage

def test_partial_tp_risk_decision():
    inst = Instrument(
        symbol="SOL/USDT", category="breakout", strategy_name="breakout",
        strategy_params={}, stop_loss_pct=0.08, take_profit_pct=0.30,
        position_size_pct=0.20, partial_take_profit_pct=0.05, partial_take_profit_ratio=0.5
    )
    risk_cfg = RiskConfig()
    rm = RiskManager(risk_cfg)

    pos = rm.build_position(inst, Side.BUY, amount=10.0, entry_price=100.0, entry_fee=0.1, reason="test")
    assert pos.partial_tp_pct == 0.05
    assert pos.partial_tp_ratio == 0.5
    assert pos.partial_tp_done is False
    assert pos.stop_loss == 92.0

    # Precio en 103 (3%): no debe activar TP parcial
    dec1 = rm.evaluate_exit(pos, 103.0)
    assert dec1.order is None

    # Precio en 105 (5%): debe activar TP parcial del 50% (amount=5.0)
    dec2 = rm.evaluate_exit(pos, 105.0)
    assert dec2.order is not None
    assert dec2.order.reason == "partial-take-profit"
    assert dec2.order.amount == 5.0

def test_engine_executes_partial_tp(tmp_path):
    db_path = str(tmp_path / "test.db")
    storage = Storage(db_path)

    config = MagicMock(spec=Config)
    config.risk = RiskConfig(starting_balance=1000.0, quote_currency="USDT")
    config.mode = "paper"
    config.effective_db_path.return_value = db_path

    inst = Instrument(
        symbol="SOL/USDT", category="breakout_diario", strategy_name="breakout",
        strategy_params={}, stop_loss_pct=0.08, take_profit_pct=0.30,
        position_size_pct=0.20, partial_take_profit_pct=0.05, partial_take_profit_ratio=0.5
    )
    config.instrument.return_value = inst

    from tradebot.models import Fill

    execution = MagicMock()
    execution.get_balance.return_value = 1000.0
    execution.execute.side_effect = lambda order: Fill(
        order=order, filled_price=order.price, filled_amount=order.amount, fee=0.05
    )

    rm = RiskManager(config.risk)
    notifier = MagicMock()

    engine = Engine(config, {}, rm, execution, storage, notifier=notifier)

    pos = rm.build_position(inst, Side.BUY, amount=10.0, entry_price=100.0, entry_fee=0.1, reason="test_entry")
    engine.positions.append(pos)
    storage.save_open_position(pos)

    # Simular precio en 105 (+5%)
    engine._check_exits("SOL/USDT", 105.0)

    # Verificar que la posición abierta sigue existiendo pero reducida al 50% y con SL en Breakeven (100.0)
    assert len(engine.positions) == 1
    rem_pos = engine.positions[0]
    assert rem_pos.amount == 5.0
    assert rem_pos.partial_tp_done is True
    assert rem_pos.stop_loss == 100.0   # Breakeven!

    # Verificar que se registró la operación parcial cerrada
    assert len(engine.closed_trades) == 1
    closed = engine.closed_trades[0]
    assert closed.amount == 5.0
    assert closed.exit_price == 105.0
    assert closed.exit_reason == "partial-take-profit"
    assert closed.pnl_abs > 0
