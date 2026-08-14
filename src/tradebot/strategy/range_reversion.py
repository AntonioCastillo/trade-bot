"""Estrategia de reversión a la media para mercados laterales (Range-Bound).

Busca comprar en soportes del rango (Banda Inferior de Bollinger) y vender/corto
en resistencias (Banda Superior de Bollinger) únicamente cuando el ADX confirma
que la tendencia es débil (ADX <= adx_max, por ejemplo < 25).
"""

from __future__ import annotations

import pandas as pd

from .. import indicators
from ..models import Signal, SignalType
from .base import Strategy


class RangeReversionStrategy(Strategy):
    def __init__(
        self,
        adx_period: int = 14,
        adx_max: float = 25.0,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        bb_period: int = 20,
        bb_std: float = 2.0,
        bidirectional: bool = False,
    ):
        self.adx_period = adx_period
        self.adx_max = adx_max
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.bidirectional = bidirectional
        self.min_candles = max(adx_period, rsi_period, bb_period) + 3

    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal:
        close = candles["close"]
        last_price = float(close.iloc[-1])

        if len(candles) < self.min_candles:
            return Signal(
                SignalType.HOLD, symbol, last_price,
                reason=f"insuficientes velas ({len(candles)}/{self.min_candles})",
            )

        # 1. Medir fuerza de la tendencia con ADX
        adx_series = indicators.adx(candles["high"], candles["low"], close, self.adx_period)
        last_adx = float(adx_series.iloc[-1])

        if last_adx > self.adx_max:
            return Signal(
                SignalType.HOLD, symbol, last_price,
                reason=f"mercado en tendencia: ADX {last_adx:.1f} > {self.adx_max}",
            )

        # 2. Obtener oscilador RSI y bandas de Bollinger
        rsi_series = indicators.rsi(close, self.rsi_period)
        bb_df = indicators.bollinger_bands(close, self.bb_period, self.bb_std)

        last_rsi = float(rsi_series.iloc[-1])
        lower_band = float(bb_df["lower"].iloc[-1])
        upper_band = float(bb_df["upper"].iloc[-1])

        # Compra: sobreventa en rango y precio bajo la banda inferior
        if last_rsi <= self.rsi_oversold and last_price <= lower_band:
            return Signal(
                SignalType.BUY, symbol, last_price,
                reason=f"rango compra: RSI {last_rsi:.1f} y precio <= banda inferior {lower_band:.6f} (ADX {last_adx:.1f})",
            )

        # Venta corta: sobrecompra en rango y precio sobre la banda superior (si es bidireccional)
        if self.bidirectional and last_rsi >= self.rsi_overbought and last_price >= upper_band:
            return Signal(
                SignalType.SELL, symbol, last_price,
                reason=f"rango venta: RSI {last_rsi:.1f} y precio >= banda superior {upper_band:.6f} (ADX {last_adx:.1f})",
            )

        return Signal(
            SignalType.HOLD, symbol, last_price,
            reason=f"rango neutral: RSI {last_rsi:.1f}, precio {last_price:.6f} entre bandas [{lower_band:.6f}, {upper_band:.6f}]",
        )
