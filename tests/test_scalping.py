import numpy as np
import pandas as pd

from tradebot.models import SignalType
from tradebot.strategy.scalping import ScalpingStrategy


def _df(prices):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="1min", tz="UTC")
    close = pd.Series(prices, index=idx)
    return pd.DataFrame({
        "open": close, "high": close * 1.001, "low": close * 0.999,
        "close": close, "volume": np.full(len(prices), 100.0),
    })


def test_hold_without_enough_candles():
    s = ScalpingStrategy(ema_fast=5, ema_slow=20)
    assert s.generate_signal("X", _df([100.0] * 10)).type is SignalType.HOLD


def test_buy_on_bullish_cross():
    # Plano y luego subida sostenida -> la EMA rápida cruza por encima de la lenta.
    prices = [100.0] * 30 + [100.5, 101, 101.8, 102.5, 103.5]
    s = ScalpingStrategy(ema_fast=5, ema_slow=20)
    # Buscar el cruce en la ventana creciente.
    got_buy = any(
        s.generate_signal("X", _df(prices[:i])).type is SignalType.BUY
        for i in range(s.min_candles, len(prices) + 1)
    )
    assert got_buy


def test_no_buy_when_flat():
    prices = [100.0] * 60  # precio constante -> las EMAs no se cruzan
    s = ScalpingStrategy(ema_fast=5, ema_slow=20)
    sig = s.generate_signal("X", _df(prices))
    assert sig.type is SignalType.HOLD


def test_min_gap_filters_weak_cross():
    prices = [100.0] * 30 + [100.5, 101, 101.8, 102.5, 103.5]
    # Exigir 50% de separación EMA -> imposible -> nunca compra.
    s = ScalpingStrategy(ema_fast=5, ema_slow=20, min_gap_pct=0.5)
    got_buy = any(
        s.generate_signal("X", _df(prices[:i])).type is SignalType.BUY
        for i in range(s.min_candles, len(prices) + 1)
    )
    assert not got_buy
