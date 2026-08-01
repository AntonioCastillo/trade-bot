"""Interfaz común de las estrategias."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from ..models import Signal


class Strategy(ABC):
    """Una estrategia recibe el histórico de velas y emite una única señal.

    No conoce el balance ni el riesgo: sólo decide dirección (BUY/SELL/HOLD).
    El dimensionamiento y las salidas los gestiona el RiskManager.
    """

    #: nº mínimo de velas necesarias para producir una señal fiable.
    min_candles: int = 1

    @abstractmethod
    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal:
        """`candles` es un DataFrame OHLCV indexado por tiempo (orden ascendente)."""
        raise NotImplementedError
