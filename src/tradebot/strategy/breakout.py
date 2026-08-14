"""Breakout / momentum-continuación (canal de Donchian).

Compra cuando el precio ROMPE por encima del máximo de las últimas `lookback`
velas — sigue la fuerza, no la revierte. El edge-scanner mostró que en 4h estos
activos tienden a continuar tras romper máximos. Solo-largos; salida por el
RiskManager (take-profit / stop / trailing).

NO es consejo. Validar con walk-forward antes de usar.
"""

from __future__ import annotations

import pandas as pd

from .. import indicators
from ..models import Signal, SignalType
from .base import Strategy


class BreakoutStrategy(Strategy):
    def __init__(self, lookback: int = 20, bidirectional: bool = False, min_bb_width: float = 0.0):
        self.lookback = lookback
        self.bidirectional = bidirectional
        self.min_bb_width = min_bb_width
        self.min_candles = max(lookback + 2, 21)

    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal:
        close = candles["close"]
        last_price = float(close.iloc[-1])

        if len(candles) < self.min_candles:
            return Signal(SignalType.HOLD, symbol, last_price, reason="sin datos")

        # Filtro de compresión de volatilidad (Bollinger Squeeze)
        if self.min_bb_width > 0:
            bb = indicators.bollinger_bands(close, period=20, num_std=2.0)
            middle = float(bb["middle"].iloc[-1])
            if middle > 0:
                width = float((bb["upper"].iloc[-1] - bb["lower"].iloc[-1]) / middle)
                if width < self.min_bb_width:
                    return Signal(
                        SignalType.HOLD, symbol, last_price,
                        reason=f"bollinger squeeze: ancho {width:.3f} < mínimo {self.min_bb_width:.3f}"
                    )

        # Máximo y mínimo del canal previo (excluye la vela actual).
        channel_high = float(close.iloc[-(self.lookback + 1):-1].max())
        channel_low = float(close.iloc[-(self.lookback + 1):-1].min())

        if last_price > channel_high:
            return Signal(
                SignalType.BUY, symbol, last_price,
                reason=f"ruptura máximo {self.lookback} velas ({channel_high:.6f})",
            )
        elif self.bidirectional and last_price < channel_low:
            return Signal(
                SignalType.SELL, symbol, last_price,
                reason=f"ruptura mínimo {self.lookback} velas ({channel_low:.6f})",
            )
        return Signal(SignalType.HOLD, symbol, last_price, reason="sin ruptura")
