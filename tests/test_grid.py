import numpy as np
import pandas as pd
from conftest import make_config, make_instrument

from tradebot.engine import Engine
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.models import Side, SignalType
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.grid import GridStrategy


def _df(prices):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="15min", tz="UTC")
    close = pd.Series(prices, index=idx)
    return pd.DataFrame({
        "open": close, "high": close * 1.001, "low": close * 0.999,
        "close": close, "volume": np.full(len(prices), 100.0),
    })


def test_hold_without_range():
    s = GridStrategy(range_period=50, levels=10)
    assert s.generate_signal("X", _df([100.0] * 10)).type is SignalType.HOLD


def test_buy_on_downward_level_cross():
    # Rango 90-110 establecido, luego el precio cae cruzando niveles hacia abajo.
    prices = [90 + (i % 21) for i in range(60)]   # oscila 90..110
    prices += [105, 100]                            # baja cruzando niveles
    s = GridStrategy(range_period=50, levels=10)
    sig = s.generate_signal("X", _df(prices))
    assert sig.type is SignalType.BUY


def test_hold_when_price_rises():
    prices = [90 + (i % 21) for i in range(60)] + [100, 106]  # sube
    s = GridStrategy(range_period=50, levels=10)
    sig = s.generate_signal("X", _df(prices))
    assert sig.type is SignalType.HOLD


def test_grid_allows_multiple_positions_same_symbol():
    # Con max_concurrent_per_symbol alto, el motor mantiene varios peldaños.
    ins = make_instrument(
        symbol="BTC/USDT", strategy_name="grid",
        stop_loss_pct=0.20, take_profit_pct=0.02, position_size_pct=0.05,
    )
    ins.max_concurrent_per_symbol = 5
    config = make_config(ins, starting_balance=10_000)
    strat = GridStrategy(range_period=50, levels=10)
    risk = RiskManager(config.risk)
    engine = Engine(config, {"BTC/USDT": strat}, risk, PaperExecutionEngine(config),
                    Storage(":memory:"), enforce_daily_loss=False)

    # Secuencia bajista escalonada -> varios cruces a la baja -> varias compras.
    prices = [90 + (i % 21) for i in range(60)] + [108, 104, 100, 96, 92]
    for i in range(strat.min_candles, len(prices) + 1):
        engine.process("BTC/USDT", _df(prices[:i]))

    longs = [p for p in engine.positions if p.side is Side.BUY]
    assert len(longs) >= 2   # mantiene varios peldaños a la vez
