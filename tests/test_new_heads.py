import numpy as np
import pandas as pd

from tradebot.models import SignalType
from tradebot.pairs import analyze_pair, ratio_zscore
from tradebot.strategy.breakout import BreakoutStrategy
from tradebot.strategy.trend import TrendStrategy


def _df(prices, freq="4h"):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq=freq, tz="UTC")
    close = pd.Series(prices, index=idx)
    return pd.DataFrame({
        "open": close.shift(1).fillna(close), "high": close * 1.001,
        "low": close * 0.999, "close": close, "volume": np.full(len(prices), 100.0),
    })


# --- Breakout -----------------------------------------------------------------

def test_breakout_buys_on_new_high():
    prices = [100.0] * 30 + [105]     # rompe el máximo del canal
    sig = BreakoutStrategy(lookback=20).generate_signal("BTC/USDT", _df(prices))
    assert sig.type is SignalType.BUY


def test_breakout_holds_inside_channel():
    prices = [100.0 + (i % 5) * 0.1 for i in range(40)]  # dentro del rango
    sig = BreakoutStrategy(lookback=20).generate_signal("BTC/USDT", _df(prices))
    assert sig.type is SignalType.HOLD


# --- Trend --------------------------------------------------------------------

def test_trend_buys_on_golden_cross():
    # Plano y luego subida sostenida -> la SMA rápida cruza sobre la lenta.
    prices = [100.0] * 60 + list(np.linspace(100, 130, 20))
    strat = TrendStrategy(fast=10, slow=50)
    got = any(
        strat.generate_signal("BTC/USDT", _df(prices[:i], "1d")).type is SignalType.BUY
        for i in range(strat.min_candles, len(prices) + 1)
    )
    assert got


def test_trend_holds_when_flat():
    prices = [100.0] * 120
    sig = TrendStrategy(fast=10, slow=50).generate_signal("BTC/USDT", _df(prices, "1d"))
    assert sig.type is SignalType.HOLD


# --- Pairs --------------------------------------------------------------------

def test_ratio_zscore_zero_when_constant_ratio():
    a = pd.Series(np.arange(1, 101, dtype=float))
    b = pd.Series(np.arange(1, 101, dtype=float)) * 2   # ratio constante 0.5
    _, z = ratio_zscore(a, b, 20)
    zz = z.dropna()
    # Con ratio constante, la desviación es 0 -> z es NaN (0/0) o ~0.
    assert zz.empty or float(zz.abs().max()) < 1e-6


def test_analyze_pair_runs_and_counts():
    rng = np.random.default_rng(0)
    a = _df(list(100 + rng.standard_normal(300).cumsum()))
    b = _df(list(100 + rng.standard_normal(300).cumsum()))
    res = analyze_pair(a, b, lookback=50, entry_z=1.5)
    assert res.count >= 0
    assert set(res.mean_spread_fwd.keys()) == {1, 3, 5, 10}
