"""Estrategias archivadas (legacy / retiradas).

Mantenidas para reproducción de backtests históricos y compatibilidad regresiva.
"""

from __future__ import annotations

from .mean_reversion import MeanReversionStrategy
from .rsi_scalper import RsiScalperStrategy
from .scalping import ScalpingStrategy

__all__ = [
    "MeanReversionStrategy",
    "RsiScalperStrategy",
    "ScalpingStrategy",
]
