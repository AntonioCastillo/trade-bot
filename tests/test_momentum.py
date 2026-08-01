import numpy as np
import pandas as pd

from tradebot.models import SignalType
from tradebot.strategy.momentum import MomentumStrategy


def _df(prices, volumes=None):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="1h", tz="UTC")
    close = pd.Series(prices, index=idx)
    vol = volumes if volumes is not None else [100.0] * len(prices)
    return pd.DataFrame(
        {
            "open": close.shift(1).fillna(close),
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": pd.Series(vol, index=idx),
        }
    )


def _strat(**kw):
    base = dict(fast_ema=10, slow_ema=30, breakout_lookback=20,
                atr_period=14, breakout_atr_mult=0.5, min_trend_strength=0.0,
                volume_mult=1.0)
    base.update(kw)
    return MomentumStrategy(**base)


def test_hold_when_not_enough_candles():
    sig = _strat().generate_signal("DOGE/USDT", _df([1.0] * 10))
    assert sig.type is SignalType.HOLD


def test_buy_on_strong_breakout_with_volume():
    prices = [1.0] * 40 + [1.05, 1.10, 1.18, 1.25, 1.35]
    volumes = [100.0] * 44 + [300.0]  # ruptura con volumen alto
    sig = _strat().generate_signal("DOGE/USDT", _df(prices, volumes))
    assert sig.type is SignalType.BUY


def test_downward_move_is_hold_not_short():
    # Long-only: una caída NO abre corto, devuelve HOLD.
    prices = [1.0] * 40 + [0.95, 0.90, 0.82, 0.75, 0.65]
    sig = _strat().generate_signal("DOGE/USDT", _df(prices))
    assert sig.type is SignalType.HOLD


def test_hold_inside_channel():
    prices = [1.0 + (i % 3 - 1) * 0.001 for i in range(60)]
    sig = _strat().generate_signal("DOGE/USDT", _df(prices))
    assert sig.type is SignalType.HOLD


def test_atr_filter_rejects_marginal_breakout():
    # Con un múltiplo de ATR muy alto, ninguna ruptura razonable entra.
    prices = [1.0] * 40 + [1.05, 1.10, 1.18, 1.25, 1.35]
    sig = _strat(breakout_atr_mult=50.0).generate_signal("DOGE/USDT", _df(prices))
    assert sig.type is SignalType.HOLD


def test_volume_filter_rejects_low_volume_breakout():
    prices = [1.0] * 40 + [1.05, 1.10, 1.18, 1.25, 1.35]
    volumes = [100.0] * 44 + [10.0]  # rompe pero SIN volumen
    sig = _strat(volume_mult=1.2).generate_signal("DOGE/USDT", _df(prices, volumes))
    assert sig.type is SignalType.HOLD


def test_trend_strength_filter_rejects_weak_trend():
    prices = [1.0] * 40 + [1.05, 1.10, 1.18, 1.25, 1.35]
    volumes = [100.0] * 44 + [300.0]
    # Exigir 50% de separación de EMAs -> imposible aquí -> HOLD.
    sig = _strat(min_trend_strength=0.5).generate_signal("DOGE/USDT", _df(prices, volumes))
    assert sig.type is SignalType.HOLD
