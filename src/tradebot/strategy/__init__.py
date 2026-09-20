"""Estrategias de trading. Registro simple por nombre."""

from __future__ import annotations

from typing import Any

from .base import Strategy
from .breakout import BreakoutStrategy
from .capitulation import CapitulationStrategy
from .grid import GridStrategy
from .legacy import MeanReversionStrategy, RsiScalperStrategy, ScalpingStrategy
from .momentum import MomentumStrategy
from .range_reversion import RangeReversionStrategy
from .trend import TrendStrategy
from .volume_surge import VolumeSurgeStrategy

_REGISTRY: dict[str, type[Strategy]] = {
    # Estrategias Activas Hydra
    "breakout": BreakoutStrategy,
    "capitulation": CapitulationStrategy,
    "grid": GridStrategy,
    "momentum": MomentumStrategy,
    "range_reversion": RangeReversionStrategy,
    "trend": TrendStrategy,
    "volume_surge": VolumeSurgeStrategy,
    # Estrategias Archivadas (Legacy)
    "mean_reversion": MeanReversionStrategy,
    "rsi_scalper": RsiScalperStrategy,
    "scalping": ScalpingStrategy,
}


def build_strategy(name: str, params: dict[str, Any] | None = None) -> Strategy:
    try:
        cls = _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Estrategia desconocida: {name!r}. "
            f"Disponibles: {sorted(_REGISTRY)}"
        ) from None
    return cls(**(params or {}))


__all__ = [
    "Strategy",
    "MeanReversionStrategy",
    "MomentumStrategy",
    "VolumeSurgeStrategy",
    "GridStrategy",
    "ScalpingStrategy",
    "BreakoutStrategy",
    "TrendStrategy",
    "CapitulationStrategy",
    "RangeReversionStrategy",
    "RsiScalperStrategy",
    "build_strategy",
]
