"""Scalping — entradas y salidas rápidas en marcos cortos (1m/5m).

Entra al cruce alcista de una EMA rápida sobre una lenta (impulso corto) y sale
enseguida con TP/SL MUY ajustados (configurados en el instrumento). Solo-largos.

Aviso honesto: el scalping vive o muere por las comisiones. Con TP/SL de décimas
de %, cada ida y vuelta a mercado (taker) paga ~0,3% (comisión+slippage), así que
el margen tiene que superar eso. Validar SIEMPRE con comisiones reales; el
resultado del backtest es hipersensible al modelo de costes.
"""

from __future__ import annotations

import pandas as pd

from ..models import Signal, SignalType
from .base import Strategy


class ScalpingStrategy(Strategy):
    def __init__(self, ema_fast: int = 5, ema_slow: int = 20, min_gap_pct: float = 0.0):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.min_gap_pct = min_gap_pct
        self.min_candles = ema_slow + 2

    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal:
        close = candles["close"]
        last_price = float(close.iloc[-1])

        if len(candles) < self.min_candles:
            return Signal(SignalType.HOLD, symbol, last_price, reason="sin datos")

        fast = close.ewm(span=self.ema_fast, adjust=False).mean()
        slow = close.ewm(span=self.ema_slow, adjust=False).mean()
        fast_now, fast_prev = float(fast.iloc[-1]), float(fast.iloc[-2])
        slow_now, slow_prev = float(slow.iloc[-1]), float(slow.iloc[-2])

        # Cruce alcista fresco (la rápida cruza por encima de la lenta) con una
        # separación mínima opcional para filtrar cruces de ruido.
        crossed_up = fast_prev <= slow_prev and fast_now > slow_now
        gap_ok = slow_now > 0 and (fast_now - slow_now) / slow_now >= self.min_gap_pct

        if crossed_up and gap_ok:
            return Signal(
                SignalType.BUY, symbol, last_price,
                reason=f"scalp: cruce EMA{self.ema_fast}>EMA{self.ema_slow}",
            )

        return Signal(SignalType.HOLD, symbol, last_price, reason="scalp: sin cruce")
