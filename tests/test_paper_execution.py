import pytest
from conftest import make_config, make_instrument

from tradebot.execution.paper import PaperExecutionEngine
from tradebot.models import Order, Side


def _config(slippage: float = 0.0):
    return make_config(make_instrument(), slippage=slippage, starting_balance=10_000)


def test_buy_reduces_balance_with_fee():
    engine = PaperExecutionEngine(_config())
    engine.execute(Order("BTC/USDT", Side.BUY, amount=1.0, price=1000.0))
    # 10.000 - 1.000 (notional) - 1.0 (fee 0.1%) = 8.999
    assert engine.get_balance() == 8_999.0


def test_sell_increases_balance_with_fee():
    engine = PaperExecutionEngine(_config())
    engine.execute(Order("BTC/USDT", Side.SELL, amount=1.0, price=1000.0))
    # 10.000 + 1.000 - 1.0 = 10.999
    assert engine.get_balance() == 10_999.0


def test_slippage_worsens_fill_price():
    engine = PaperExecutionEngine(_config(slippage=0.001))
    buy = engine.execute(Order("BTC/USDT", Side.BUY, amount=1.0, price=1000.0))
    sell = engine.execute(Order("BTC/USDT", Side.SELL, amount=1.0, price=1000.0))
    assert buy.filled_price == pytest.approx(1001.0)   # compra por encima
    assert sell.filled_price == pytest.approx(999.0)   # venta por debajo


def test_fill_reports_amount():
    engine = PaperExecutionEngine(_config())
    fill = engine.execute(Order("BTC/USDT", Side.BUY, amount=0.5, price=2000.0))
    assert fill.filled_amount == 0.5
    assert fill.fee == 1.0
