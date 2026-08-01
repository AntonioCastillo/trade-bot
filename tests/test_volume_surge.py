import numpy as np
import pandas as pd

from tradebot.models import SignalType
from tradebot.strategy.volume_surge import VolumeSurgeStrategy


def _df(prices, volumes):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="15min", tz="UTC")
    close = pd.Series(prices, index=idx)
    return pd.DataFrame({
        "open": close.shift(1).fillna(close), "high": close * 1.001,
        "low": close * 0.999, "close": close,
        "volume": pd.Series(volumes, index=idx),
    })


def test_hold_without_enough_candles():
    s = VolumeSurgeStrategy(vol_period=20)
    assert s.generate_signal("X", _df([1.0] * 5, [1] * 5)).type is SignalType.HOLD


def test_buy_on_volume_surge_with_rising_price():
    prices = [1.0] * 25 + [1.03]           # última vela sube
    volumes = [100.0] * 25 + [400.0]        # y con volumen x4
    s = VolumeSurgeStrategy(vol_period=20, surge_mult=2.5)
    assert s.generate_signal("X", _df(prices, volumes)).type is SignalType.BUY


def test_no_buy_on_surge_but_falling_price():
    prices = [1.0] * 25 + [0.97]           # volumen alto pero PRECIO CAE
    volumes = [100.0] * 25 + [400.0]
    s = VolumeSurgeStrategy(vol_period=20, surge_mult=2.5)
    assert s.generate_signal("X", _df(prices, volumes)).type is SignalType.HOLD


def test_no_buy_without_surge():
    prices = [1.0] * 25 + [1.03]
    volumes = [100.0] * 26                  # volumen normal, sin explosión
    s = VolumeSurgeStrategy(vol_period=20, surge_mult=2.5)
    assert s.generate_signal("X", _df(prices, volumes)).type is SignalType.HOLD
