"""Grid trading — pensado para mercados LATERALES (en rango).

Divide un rango de precio reciente en `levels` niveles equiespaciados. Cada vez
que el precio cruza HACIA ABAJO a un nivel inferior, compra un "peldaño". El
motor cierra cada peldaño por take-profit (configúralo ~1 paso de rejilla) y el
stop-loss cubre la ruptura del rango por abajo. Solo-largos (spot).

Necesita `max_concurrent_per_symbol > 1` para sostener varios peldaños a la vez.

Ideal cuando el precio oscila en un rango; peligroso si rompe en tendencia (por
eso el stop). NO es consejo: validar con walk-forward antes de usar.
"""

from __future__ import annotations

import pandas as pd

from ..models import Signal, SignalType
from .base import Strategy


class GridStrategy(Strategy):
    def __init__(self, range_period: int = 100, levels: int = 10):
        self.range_period = range_period
        self.levels = max(2, levels)
        self.min_candles = range_period + 2

    def _cell(self, price: float, low: float, step: float) -> int:
        return int((price - low) // step)

    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal:
        close = candles["close"]
        last_price = float(close.iloc[-1])

        if len(candles) < self.min_candles:
            return Signal(SignalType.HOLD, symbol, last_price, reason="sin rango aún")

        window = close.iloc[-(self.range_period + 1):-1]  # rango previo (sin vela actual)
        low = float(window.min())
        high = float(window.max())
        if high <= low:
            return Signal(SignalType.HOLD, symbol, last_price, reason="rango plano")

        step = (high - low) / self.levels
        prev_price = float(close.iloc[-2])

        # Compra si el precio ha cruzado a un nivel INFERIOR de la rejilla y sigue
        # dentro del rango (no perseguimos rupturas por abajo).
        cur_cell = self._cell(last_price, low, step)
        prev_cell = self._cell(prev_price, low, step)
        if cur_cell < prev_cell and low <= last_price <= high:
            return Signal(
                SignalType.BUY, symbol, last_price,
                reason=f"grid: baja a nivel {cur_cell}/{self.levels} "
                       f"[{low:.6f}-{high:.6f}]",
            )

        return Signal(
            SignalType.HOLD, symbol, last_price,
            reason=f"grid: en nivel {cur_cell}/{self.levels}, sin cruce a la baja",
        )
