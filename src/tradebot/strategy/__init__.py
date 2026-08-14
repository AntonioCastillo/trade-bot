"""Estrategias de trading. Registro simple por nombre."""

from __future__ import annotations

from typing import Any

from .base import Strategy
from .breakout import BreakoutStrategy
from .grid import GridStrategy
from .mean_reversion import MeanReversionStrategy
from .momentum import MomentumStrategy
from .scalping import ScalpingStrategy
from .trend import TrendStrategy
from .volume_surge import VolumeSurgeStrategy
from .capitulation import CapitulationStrategy
from .range_reversion import RangeReversionStrategy
from .rsi_scalper import RsiScalperStrategy

_REGISTRY: dict[str, type[Strategy]] = {
    "mean_reversion": MeanReversionStrategy,
    "momentum": MomentumStrategy,
    "volume_surge": VolumeSurgeStrategy,
    "grid": GridStrategy,
    "scalping": ScalpingStrategy,
    "breakout": BreakoutStrategy,
    "trend": TrendStrategy,
    "capitulation": CapitulationStrategy,
    "range_reversion": RangeReversionStrategy,
    "rsi_scalper": RsiScalperStrategy,
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
