"""Estrategia de reversión a la media (RSI + Bandas de Bollinger).

Idea: los precios tienden a volver a su media. Compramos cuando el mercado
está sobrevendido (RSI bajo y precio bajo la banda inferior). SOLO-LARGOS
(spot): en sobrecompra no abrimos corto; la salida del largo la decide el
RiskManager (take-profit / stop-loss).

NOTA: esto NO es consejo de inversión. Es una plantilla técnica que debes
validar con backtesting y paper trading antes de arriesgar capital real.
"""

from __future__ import annotations

import pandas as pd

from .. import indicators
from ..models import Signal, SignalType
from .base import Strategy


class MeanReversionStrategy(Strategy):
    def __init__(
        self,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        bb_period: int = 20,
        bb_std: float = 2.0,
    ):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.bb_period = bb_period
        self.bb_std = bb_std
        # necesitamos suficientes velas para que ambos indicadores estén "calientes".
        self.min_candles = max(rsi_period, bb_period) + 1

    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal:
        close = candles["close"]
        last_price = float(close.iloc[-1])

        if len(candles) < self.min_candles:
            return Signal(
                SignalType.HOLD, symbol, last_price,
                reason=f"insuficientes velas ({len(candles)}/{self.min_candles})",
            )

        rsi = indicators.rsi(close, self.rsi_period)
        bb = indicators.bollinger_bands(close, self.bb_period, self.bb_std)

        last_rsi = float(rsi.iloc[-1])
        lower = float(bb["lower"].iloc[-1])
        upper = float(bb["upper"].iloc[-1])

        # Compra: sobreventa confirmada por RSI y por romper la banda inferior.
        if last_rsi <= self.rsi_oversold and last_price <= lower:
            return Signal(
                SignalType.BUY, symbol, last_price,
                reason=f"RSI={last_rsi:.1f}<= {self.rsi_oversold} y precio<= banda inf {lower:.2f}",
            )

        # SOLO-LARGOS (spot): en sobrecompra NO abrimos corto (no se puede vender
        # lo que no se tiene). La salida del largo la gestiona el RiskManager
        # (take-profit / stop-loss). Sobrecompra -> HOLD.
        if last_rsi >= self.rsi_overbought and last_price >= upper:
            return Signal(
                SignalType.HOLD, symbol, last_price,
                reason=f"sobrecompra (RSI={last_rsi:.1f}) — solo-largos, no se abre corto",
            )

        return Signal(
            SignalType.HOLD, symbol, last_price,
            reason=f"RSI={last_rsi:.1f}, precio {last_price:.2f} entre bandas [{lower:.2f}, {upper:.2f}]",
        )
