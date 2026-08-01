"""Estrategia de momentum / breakout para símbolos muy volátiles (memecoins).

SOLO-LARGOS (realista en spot: no se puede vender en corto lo que no se tiene).
Entra al alza cuando se cumplen TODOS los filtros de calidad, para evitar las
falsas rupturas que generan stop-losses en el ruido:

  1. Tendencia:   EMA rápida por encima de la lenta, con separación mínima.
  2. Ruptura:     el precio supera el máximo del canal por un múltiplo del ATR.
  3. Volumen:     la vela rompe con volumen por encima de su media reciente.

Las salidas las gestiona el RiskManager (stop, take-profit y trailing stop).
Esto NO es consejo de inversión: es una plantilla a validar con backtesting.
"""

from __future__ import annotations

import pandas as pd

from .. import indicators
from ..models import Signal, SignalType
from .base import Strategy


class MomentumStrategy(Strategy):
    def __init__(
        self,
        fast_ema: int = 10,
        slow_ema: int = 30,
        breakout_lookback: int = 20,
        atr_period: int = 14,
        breakout_atr_mult: float = 0.5,
        min_trend_strength: float = 0.0,
        volume_mult: float = 1.0,
    ):
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.breakout_lookback = breakout_lookback
        self.atr_period = atr_period
        self.breakout_atr_mult = breakout_atr_mult
        self.min_trend_strength = min_trend_strength
        self.volume_mult = volume_mult
        self.min_candles = max(slow_ema, breakout_lookback, atr_period) + 1

    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal:
        close = candles["close"]
        last_price = float(close.iloc[-1])

        if len(candles) < self.min_candles:
            return Signal(
                SignalType.HOLD, symbol, last_price,
                reason=f"insuficientes velas ({len(candles)}/{self.min_candles})",
            )

        fast = float(close.ewm(span=self.fast_ema, adjust=False).mean().iloc[-1])
        slow = float(close.ewm(span=self.slow_ema, adjust=False).mean().iloc[-1])
        atr = float(
            indicators.atr(candles["high"], candles["low"], close, self.atr_period).iloc[-1]
        )
        # Máximo del canal previo (excluye la vela actual).
        channel_high = float(close.iloc[-(self.breakout_lookback + 1):-1].max())

        # --- Filtros de calidad (todos deben cumplirse para entrar) ---------------
        trend_strength = (fast - slow) / slow if slow else 0.0
        trend_ok = fast > slow and trend_strength >= self.min_trend_strength
        breakout_level = channel_high + self.breakout_atr_mult * atr
        breakout_ok = last_price > breakout_level

        volume_ok = True
        if "volume" in candles and self.volume_mult > 0:
            vol = candles["volume"]
            avg_vol = float(vol.iloc[-(self.breakout_lookback + 1):-1].mean())
            volume_ok = avg_vol <= 0 or float(vol.iloc[-1]) >= avg_vol * self.volume_mult

        if trend_ok and breakout_ok and volume_ok:
            return Signal(
                SignalType.BUY, symbol, last_price,
                reason=(
                    f"breakout>{breakout_level:.6f} (canal {channel_high:.6f}+{self.breakout_atr_mult}·ATR), "
                    f"tendencia {trend_strength * 100:.1f}%"
                ),
            )

        # Long-only: si no hay entrada de calidad, no hacemos nada (las salidas
        # las decide el RiskManager sobre las posiciones abiertas).
        failed = []
        if not trend_ok:
            failed.append("tendencia")
        if not breakout_ok:
            failed.append("ruptura")
        if not volume_ok:
            failed.append("volumen")
        return Signal(
            SignalType.HOLD, symbol, last_price,
            reason=f"sin entrada (falla: {', '.join(failed)})",
        )
