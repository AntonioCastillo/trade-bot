import numpy as np
import pandas as pd
import pytest

from tradebot.models import SignalType
from tradebot.strategy.range_reversion import RangeReversionStrategy
from tradebot.strategy.breakout import BreakoutStrategy
from tradebot.strategy.momentum import MomentumStrategy


def _df(prices, highs=None, lows=None, volumes=None):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="1h", tz="UTC")
    close = pd.Series(prices, index=idx)
    high = pd.Series(highs, index=idx) if highs is not None else close * 1.001
    low = pd.Series(lows, index=idx) if lows is not None else close * 0.999
    vol = pd.Series(volumes, index=idx) if volumes is not None else pd.Series([100.0] * len(prices), index=idx)
    return pd.DataFrame(
        {
            "open": close.shift(1).fillna(close),
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
        }
    )


def test_range_reversion_trending_adx():
    # Mercado en tendencia alcista fuerte -> ADX será alto
    prices = [1.0 + i * 0.05 for i in range(40)]
    strategy = RangeReversionStrategy(adx_max=25.0)
    sig = strategy.generate_signal("BTC/USDT", _df(prices))
    assert sig.type is SignalType.HOLD
    assert "mercado en tendencia" in sig.reason


def test_range_reversion_buy_signal():
    # Mercado lateral (precios oscilando) con un dip final para romper banda inferior y RSI bajo
    prices = [100.0 if i % 2 == 0 else 102.0 for i in range(40)]
    prices[-1] = 95.0  # dip fuerte para romper banda
    # Ajustamos rsi_oversold=45.0 para que se dispare con el RSI real obtenido (~43.0)
    strategy = RangeReversionStrategy(adx_max=35.0, rsi_oversold=45.0)
    sig = strategy.generate_signal("BTC/USDT", _df(prices))
    assert sig.type is SignalType.BUY
    assert "rango compra" in sig.reason


def test_range_reversion_sell_signal():
    # Mercado lateral con pico final para romper banda superior y RSI alto
    prices = [100.0 if i % 2 == 0 else 98.0 for i in range(40)]
    prices[-1] = 105.0  # pico
    # Ajustamos rsi_overbought=55.0 para que se dispare con el RSI real obtenido (~57.0)
    strategy = RangeReversionStrategy(adx_max=35.0, rsi_overbought=55.0, bidirectional=True)
    sig = strategy.generate_signal("BTC/USDT", _df(prices))
    assert sig.type is SignalType.SELL
    assert "rango venta" in sig.reason


def test_breakout_squeeze_filter():
    # Precios extremadamente comprimidos: Bollinger Band width es muy pequeño
    prices = [100.0] * 40
    # amago de ruptura al final
    prices[-1] = 100.2
    strategy = BreakoutStrategy(lookback=10, min_bb_width=0.01)
    sig = strategy.generate_signal("BTC/USDT", _df(prices))
    assert sig.type is SignalType.HOLD
    assert "bollinger squeeze" in sig.reason


def test_momentum_squeeze_filter():
    prices = [100.0] * 40
    prices[-1] = 100.2
    strategy = MomentumStrategy(
        fast_ema=5, slow_ema=15, breakout_lookback=10,
        atr_period=10, breakout_atr_mult=0.1, min_trend_strength=0.0,
        volume_mult=0.0, bidirectional=True, min_bb_width=0.01
    )
    sig = strategy.generate_signal("BTC/USDT", _df(prices))
    assert sig.type is SignalType.HOLD
    assert "bollinger squeeze" in sig.reason
