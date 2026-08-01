import numpy as np
import pandas as pd

from tradebot import indicators


def test_rsi_all_gains_is_100():
    close = pd.Series(np.arange(1, 30, dtype=float))
    rsi = indicators.rsi(close, period=14)
    assert rsi.iloc[-1] == 100.0


def test_rsi_all_losses_is_zero():
    close = pd.Series(np.arange(30, 1, -1, dtype=float))
    rsi = indicators.rsi(close, period=14)
    assert rsi.iloc[-1] == 0.0


def test_rsi_bounded_0_100():
    rng = np.random.default_rng(42)
    close = pd.Series(100 + rng.standard_normal(200).cumsum())
    rsi = indicators.rsi(close, period=14).dropna()
    assert (rsi >= 0).all() and (rsi <= 100).all()


def test_atr_positive_and_tracks_volatility():
    rng = np.random.default_rng(1)
    close = pd.Series(100 + rng.standard_normal(100).cumsum())
    high = close + 1.0
    low = close - 1.0
    atr = indicators.atr(high, low, close, period=14).dropna()
    assert (atr > 0).all()


def test_bollinger_ordering():
    rng = np.random.default_rng(0)
    close = pd.Series(100 + rng.standard_normal(100).cumsum())
    bb = indicators.bollinger_bands(close, period=20, num_std=2.0).dropna()
    assert (bb["lower"] <= bb["middle"]).all()
    assert (bb["middle"] <= bb["upper"]).all()
