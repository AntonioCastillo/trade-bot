"""Trend-following (cruce de medias), pensado para marcos altos (1d).

Entra al cruce alcista de una media rápida sobre una lenta (golden cross) y deja
correr la tendencia; la salida la gestiona el RiskManager, idealmente con
trailing stop amplio. Opera poco → las comisiones dejan de mandar. Solo-largos.

NO es consejo. Validar con walk-forward antes de usar.
"""

from __future__ import annotations

import pandas as pd

from ..models import Signal, SignalType
from .base import Strategy


class TrendStrategy(Strategy):
    def __init__(self, fast: int = 20, slow: int = 50):
        self.fast = fast
        self.slow = slow
        self.min_candles = slow + 2

    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal:
        close = candles["close"]
        last_price = float(close.iloc[-1])

        if len(candles) < self.min_candles or self.fast >= self.slow:
            return Signal(SignalType.HOLD, symbol, last_price, reason="sin datos/params")

        fast_ma = close.rolling(self.fast).mean()
        slow_ma = close.rolling(self.slow).mean()
        crossed_up = (
            float(fast_ma.iloc[-2]) <= float(slow_ma.iloc[-2])
            and float(fast_ma.iloc[-1]) > float(slow_ma.iloc[-1])
        )
        if crossed_up:
            return Signal(
                SignalType.BUY, symbol, last_price,
                reason=f"golden cross SMA{self.fast}>SMA{self.slow}",
            )
        return Signal(SignalType.HOLD, symbol, last_price, reason="sin cruce de tendencia")
