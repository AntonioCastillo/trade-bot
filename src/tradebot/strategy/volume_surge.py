"""Estrategia de explosión de volumen (volume surge) — agresiva y de mayor
frecuencia. Pensada para "seguir el dinero": entra cuando una vela rompe con
un volumen muy por encima de su media reciente Y el precio sube (para acompañar
el impulso, no cazar una caída con volumen de pánico).

Solo-largos (spot). Las salidas las gestiona el RiskManager (stop + take-profit
alto + trailing stop), ideal para pumps: cortar rápido si falla, dejar correr si
acierta.

NO validada de origen: pásala por el walk-forward antes de fiarte. NO es consejo.
"""

from __future__ import annotations

import pandas as pd

from ..models import Signal, SignalType
from .base import Strategy


class VolumeSurgeStrategy(Strategy):
    def __init__(
        self,
        vol_period: int = 20,
        surge_mult: float = 2.5,
        min_change_pct: float = 0.0,
    ):
        self.vol_period = vol_period
        self.surge_mult = surge_mult
        self.min_change_pct = min_change_pct
        self.min_candles = vol_period + 2

    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal:
        close = candles["close"]
        last_price = float(close.iloc[-1])

        if len(candles) < self.min_candles or "volume" not in candles:
            return Signal(SignalType.HOLD, symbol, last_price, reason="sin datos suficientes")

        vol = candles["volume"]
        avg_vol = float(vol.iloc[-(self.vol_period + 1):-1].mean())
        last_vol = float(vol.iloc[-1])
        prev_price = float(close.iloc[-2])
        change = (last_price - prev_price) / prev_price if prev_price else 0.0

        surge = avg_vol > 0 and last_vol >= avg_vol * self.surge_mult
        rising = change >= self.min_change_pct

        if surge and rising:
            mult = last_vol / avg_vol if avg_vol else 0
            return Signal(
                SignalType.BUY, symbol, last_price,
                reason=f"volumen x{mult:.1f} (>{self.surge_mult}) con precio +{change * 100:.2f}%",
            )

        return Signal(
            SignalType.HOLD, symbol, last_price,
            reason=f"sin surge (vol x{(last_vol / avg_vol) if avg_vol else 0:.1f})",
        )
