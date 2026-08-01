"""Breakout / momentum-continuación (canal de Donchian).

Compra cuando el precio ROMPE por encima del máximo de las últimas `lookback`
velas — sigue la fuerza, no la revierte. El edge-scanner mostró que en 4h estos
activos tienden a continuar tras romper máximos. Solo-largos; salida por el
RiskManager (take-profit / stop / trailing).

NO es consejo. Validar con walk-forward antes de usar.
"""

from __future__ import annotations

import pandas as pd

from ..models import Signal, SignalType
from .base import Strategy


class BreakoutStrategy(Strategy):
    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        self.min_candles = lookback + 2

    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal:
        close = candles["close"]
        last_price = float(close.iloc[-1])

        if len(candles) < self.min_candles:
            return Signal(SignalType.HOLD, symbol, last_price, reason="sin datos")

        # Máximo del canal previo (excluye la vela actual).
        channel_high = float(close.iloc[-(self.lookback + 1):-1].max())

        if last_price > channel_high:
            return Signal(
                SignalType.BUY, symbol, last_price,
                reason=f"ruptura máximo {self.lookback} velas ({channel_high:.6f})",
            )
        return Signal(SignalType.HOLD, symbol, last_price, reason="sin ruptura")
