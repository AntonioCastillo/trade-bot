"""Estrategia de scalping rápido basada en sobreextensiones del RSI (7 periodos, 15m).

Compra en sobreventa extrema (RSI <= 15) y vende en sobrecompra extrema (RSI >= 85)
para rebotes y reversiones rápidas intradía.
"""

from __future__ import annotations

import pandas as pd

from .. import indicators
from ..models import Signal, SignalType
from .base import Strategy


class RsiScalperStrategy(Strategy):
    def __init__(
        self,
        rsi_period: int = 7,
        rsi_oversold: float = 15.0,
        rsi_overbought: float = 85.0,
        bidirectional: bool = True,
    ):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.bidirectional = bidirectional
        self.min_candles = rsi_period + 2

    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal:
        close = candles["close"]
        last_price = float(close.iloc[-1])

        if len(candles) < self.min_candles:
            return Signal(
                SignalType.HOLD, symbol, last_price,
                reason=f"insuficientes velas ({len(candles)}/{self.min_candles})",
            )

        rsi_series = indicators.rsi(close, self.rsi_period)
        last_rsi = float(rsi_series.iloc[-1])

        # Señal de compra (Largo)
        if last_rsi <= self.rsi_oversold:
            return Signal(
                SignalType.BUY, symbol, last_price,
                reason=f"scalping compra: RSI {last_rsi:.1f} <= {self.rsi_oversold}",
            )

        # Señal de venta (Corto)
        if self.bidirectional and last_rsi >= self.rsi_overbought:
            return Signal(
                SignalType.SELL, symbol, last_price,
                reason=f"scalping venta: RSI {last_rsi:.1f} >= {self.rsi_overbought}",
            )

        return Signal(
            SignalType.HOLD, symbol, last_price,
            reason=f"scalping neutral: RSI {last_rsi:.1f}",
        )
