"""Tests para verificar la jerarquía y contratos de ExecutionEngine."""

from unittest.mock import MagicMock
import pytest

from tradebot.config import Config
from tradebot.execution import (
    ExecutionEngine,
    LiveExecutionEngine,
    OrderRejected,
    PaperExecutionEngine,
    build_execution_engine,
)
from tradebot.models import Order, Side


def test_execution_engine_is_abstract():
    with pytest.raises(TypeError):
        ExecutionEngine()


def test_paper_execution_engine_inherits_and_implements_interface():
    config = Config()
    engine = PaperExecutionEngine(config)
    assert isinstance(engine, ExecutionEngine)
    assert engine.get_balance() == config.risk.starting_balance
    assert engine.cancel_order("order-1", "BTC/USDT") is False
    assert engine.fetch_open_orders() == []

    # Execute a buy
    order = Order(symbol="BTC/USDT", side=Side.BUY, amount=0.1, price=50000.0)
    fill = engine.execute(order)
    assert fill.filled_amount == 0.1
    assert fill.filled_price >= 50000.0
    assert engine.get_balance() < config.risk.starting_balance


def test_live_execution_engine_inherits_and_implements_interface():
    config = Config(mode="live")
    mock_exchange = MagicMock()
    mock_exchange.fetch_balance.return_value = 1000.0
    engine = LiveExecutionEngine(config, mock_exchange)
    assert isinstance(engine, ExecutionEngine)
    assert engine.get_balance() == 1000.0
    assert engine.cancel_order("order-1", "BTC/USDT") is False
    assert engine.fetch_open_orders() == []


def test_build_execution_engine_factory():
    cfg_paper = Config(mode="paper")
    mock_exchange = MagicMock()
    eng_paper = build_execution_engine(cfg_paper, mock_exchange)
    assert isinstance(eng_paper, PaperExecutionEngine)
    assert isinstance(eng_paper, ExecutionEngine)

    cfg_live = Config(mode="live")
    eng_live = build_execution_engine(cfg_live, mock_exchange)
    assert isinstance(eng_live, LiveExecutionEngine)
    assert isinstance(eng_live, ExecutionEngine)
