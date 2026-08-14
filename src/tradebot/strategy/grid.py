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

from .. import indicators
from ..models import Signal, SignalType
from .base import Strategy


class GridStrategy(Strategy):
    def __init__(
        self,
        range_period: int = 100,
        levels: int = 10,
        adx_period: int = 14,
        adx_max: float = 25.0,
        bidirectional: bool = True,
    ):
        self.range_period = range_period
        self.levels = max(2, levels)
        self.adx_period = adx_period
        self.adx_max = adx_max
        self.bidirectional = bidirectional
        self.min_candles = max(range_period, adx_period) + 3

    def _cell(self, price: float, low: float, step: float) -> int:
        return int((price - low) // step)

    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal:
        close = candles["close"]
        last_price = float(close.iloc[-1])

        if len(candles) < self.min_candles:
            return Signal(SignalType.HOLD, symbol, last_price, reason="sin rango aún")

        # 1. Filtro de tendencia con ADX para evitar entrar en rejillas con tendencia fuerte
        adx_series = indicators.adx(candles["high"], candles["low"], close, self.adx_period)
        last_adx = float(adx_series.iloc[-1])
        if last_adx > self.adx_max:
            return Signal(
                SignalType.HOLD, symbol, last_price,
                reason=f"grid bloqueado por tendencia: ADX {last_adx:.1f} > {self.adx_max}",
            )

        window = close.iloc[-(self.range_period + 1):-1]  # rango previo (sin vela actual)
        low = float(window.min())
        high = float(window.max())
        if high <= low:
            return Signal(SignalType.HOLD, symbol, last_price, reason="rango plano")

        step = (high - low) / self.levels
        prev_price = float(close.iloc[-2])

        cur_cell = self._cell(last_price, low, step)
        prev_cell = self._cell(prev_price, low, step)

        # Compra si el precio ha cruzado a un nivel INFERIOR de la rejilla
        if cur_cell < prev_cell and low <= last_price <= high:
            return Signal(
                SignalType.BUY, symbol, last_price,
                reason=f"grid compra: baja a nivel {cur_cell}/{self.levels} "
                       f"[{low:.6f}-{high:.6f}]",
            )

        # Venta corta si el precio ha cruzado a un nivel SUPERIOR de la rejilla y bidireccional activo
        if self.bidirectional and cur_cell > prev_cell and low <= last_price <= high:
            return Signal(
                SignalType.SELL, symbol, last_price,
                reason=f"grid venta: sube a nivel {cur_cell}/{self.levels} "
                       f"[{low:.6f}-{high:.6f}]",
            )

        return Signal(
            SignalType.HOLD, symbol, last_price,
            reason=f"grid: en nivel {cur_cell}/{self.levels}, sin cruce de nivel",
        )
