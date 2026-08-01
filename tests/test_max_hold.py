import numpy as np
import pandas as pd
from conftest import make_config, make_instrument

from tradebot.engine import Engine
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.mean_reversion import MeanReversionStrategy


def _df(prices):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="1h", tz="UTC")
    close = pd.Series(prices, index=idx)
    return pd.DataFrame({
        "open": close, "high": close * 1.001, "low": close * 0.999,
        "close": close, "volume": np.full(len(prices), 100.0),
    })


def test_position_closes_by_timeout():
    # SL/TP muy amplios para que NO salte; el precio se queda plano tras abrir.
    ins = make_instrument(symbol="BTC/USDT", stop_loss_pct=0.50, take_profit_pct=0.50)
    config = make_config(ins, starting_balance=10_000)
    strat = MeanReversionStrategy(rsi_period=14, rsi_oversold=35, bb_period=20, bb_std=2.0)
    engine = Engine(config, {"BTC/USDT": strat}, RiskManager(config.risk),
                    PaperExecutionEngine(config), Storage(":memory:"),
                    enforce_daily_loss=False, max_hold_bars=3)

    # Caída que abre la posición.
    prices = [100.0] * 25 + [95, 90, 85, 80, 70]
    engine.process("BTC/USDT", _df(prices))
    assert len(engine.positions) == 1

    # Precio plano: sin TP/SL. Debe cerrar por timeout tras 3 velas.
    flat = prices[:]
    for _ in range(3):
        flat.append(70.0)
        engine.process("BTC/USDT", _df(flat))
    assert engine.positions == []
    trades = engine.storage.all_trades()
    assert trades[-1]["exit_reason"] == "timeout"
