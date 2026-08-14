import numpy as np
import pandas as pd
import pytest

from tradebot.models import SignalType
from tradebot.strategy.rsi_scalper import RsiScalperStrategy


def _df(prices):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="15min", tz="UTC")
    close = pd.Series(prices, index=idx)
    return pd.DataFrame(
        {
            "open": close.shift(1).fillna(close),
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": [100.0] * len(prices),
        }
    )


def test_rsi_scalper_buy():
    # Precios bajando fuertemente para inducir un RSI muy bajo (< 15)
    prices = [100.0 - i * 2.0 for i in range(25)]
    strategy = RsiScalperStrategy(rsi_period=7, rsi_oversold=25.0)
    sig = strategy.generate_signal("BTC/USDT", _df(prices))
    assert sig.type is SignalType.BUY
    assert "scalping compra" in sig.reason


def test_rsi_scalper_sell():
    # Precios subiendo fuertemente para inducir un RSI muy alto (> 85)
    prices = [100.0 + i * 2.0 for i in range(25)]
    strategy = RsiScalperStrategy(rsi_period=7, rsi_overbought=75.0, bidirectional=True)
    sig = strategy.generate_signal("BTC/USDT", _df(prices))
    assert sig.type is SignalType.SELL
    assert "scalping venta" in sig.reason


def test_rsi_scalper_hold():
    # Precios estables oscilando levemente para inducir un RSI neutral
    prices = [100.0 if i % 2 == 0 else 100.5 for i in range(25)]
    strategy = RsiScalperStrategy(rsi_period=7, rsi_oversold=15.0, rsi_overbought=85.0)
    sig = strategy.generate_signal("BTC/USDT", _df(prices))
    assert sig.type is SignalType.HOLD
    assert "scalping neutral" in sig.reason
