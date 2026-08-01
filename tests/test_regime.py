import numpy as np
import pandas as pd
from conftest import make_config, make_instrument

from tradebot import indicators
from tradebot.engine import Engine
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.regime import RANGING, TRENDING, UNKNOWN, classify_regime
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.mean_reversion import MeanReversionStrategy


def _df(prices):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="1h", tz="UTC")
    close = pd.Series(prices, index=idx)
    return pd.DataFrame({
        "open": close, "high": close * 1.002, "low": close * 0.998,
        "close": close, "volume": np.full(len(prices), 100.0),
    })


def test_adx_positive():
    rng = np.random.default_rng(0)
    close = pd.Series(100 + rng.standard_normal(200).cumsum())
    a = indicators.adx(close + 1, close - 1, close, 14).dropna()
    assert (a >= 0).all() and (a <= 100).all()


def test_regime_unknown_without_data():
    assert classify_regime(_df([100.0] * 5)) is UNKNOWN


def test_regime_trending_on_strong_uptrend():
    prices = list(np.linspace(100, 200, 120))  # tendencia limpia y fuerte
    assert classify_regime(_df(prices), volatile_atr_pct=0.05) is TRENDING


def test_regime_ranging_on_flat_oscillation():
    prices = [100 + (i % 4 - 1.5) * 0.3 for i in range(120)]  # lateral estrecho
    assert classify_regime(_df(prices), volatile_atr_pct=0.05) is RANGING


def test_engine_regime_gate_blocks_entry():
    # Estrategia que compraría, pero la cabeza solo opera en 'ranging' y el
    # mercado está en tendencia -> no debe entrar.
    ins = make_instrument(symbol="BTC/USDT", strategy_name="mean_reversion")
    ins.regimes = ["ranging"]
    config = make_config(ins)
    strat = MeanReversionStrategy(rsi_period=14, rsi_oversold=35, bb_period=20, bb_std=2.0)
    risk = RiskManager(config.risk)
    engine = Engine(config, {"BTC/USDT": strat}, risk, PaperExecutionEngine(config),
                    Storage(":memory:"), enforce_daily_loss=False)

    # Caída dentro de una tendencia bajista fuerte (RSI daría compra, pero régimen=trending/volatile).
    prices = list(np.linspace(200, 100, 60))
    engine.process("BTC/USDT", _df(prices))
    assert engine.positions == []   # bloqueada por el filtro de régimen
