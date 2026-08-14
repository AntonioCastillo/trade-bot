"""Estrategia de reversión a la media rápida (simulación de barrido de liquidaciones).

Busca comprar en pánicos de liquidación: caídas verticales de precio con volumen
extremo y un RSI extremadamente sobrevendido.
"""

from __future__ import annotations

import pandas as pd

from .. import indicators
from ..models import Signal, SignalType
from .base import Strategy


class CapitulationStrategy(Strategy):
    def __init__(
        self,
        rsi_period: int = 14,
        rsi_oversold: float = 15.0,
        lookback: int = 20,
        drop_pct: float = 0.05,
        volume_mult: float = 2.0,
    ):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.lookback = lookback
        self.drop_pct = drop_pct
        self.volume_mult = volume_mult
        self.min_candles = max(rsi_period, lookback) + 3

    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal:
        close = candles["close"]
        last_price = float(close.iloc[-1])

        if len(candles) < self.min_candles:
            return Signal(
                SignalType.HOLD, symbol, last_price,
                reason=f"insuficientes velas ({len(candles)}/{self.min_candles})",
            )

        rsi = indicators.rsi(close, self.rsi_period)
        last_rsi = float(rsi.iloc[-1])

        # Caída en las últimas 1 o 2 velas
        prev_price = float(close.iloc[-2])
        prev_price_2 = float(close.iloc[-3])
        max_prev = max(prev_price, prev_price_2)
        drop = (max_prev - last_price) / max_prev

        # Volumen extraordinario
        volume_ok = True
        if "volume" in candles and self.volume_mult > 0:
            vol = candles["volume"]
            avg_vol = float(vol.iloc[-(self.lookback + 1):-1].mean())
            volume_ok = avg_vol <= 0 or float(vol.iloc[-1]) >= avg_vol * self.volume_mult

        if last_rsi <= self.rsi_oversold and drop >= self.drop_pct and volume_ok:
            return Signal(
                SignalType.BUY, symbol, last_price,
                reason=f"capitulación: caída {drop * 100:.1f}%, RSI {last_rsi:.1f}<= {self.rsi_oversold}",
            )

        return Signal(SignalType.HOLD, symbol, last_price, reason="sin capitulación")
