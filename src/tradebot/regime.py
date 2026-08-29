"""Clasificador de régimen de mercado — el "cerebro" de la hidra.

Etiqueta el momento actual como:
  - "volatile"  : volatilidad alta (ATR% elevado)   -> scalping / momentum agresivo
  - "trending"  : tendencia fuerte (ADX alto)        -> momentum
  - "ranging"   : lateral (ADX bajo)                 -> reversión a la media / grid
  - "unknown"   : sin datos suficientes

Cada estrategia (instrumento) declara en qué regímenes debe operar; el motor
solo la deja ENTRAR cuando el régimen actual coincide. Así cada "cabeza" se
enciende sola cuando el mercado le favorece.
"""

from __future__ import annotations

import math

import pandas as pd

from . import indicators

VOLATILE = "volatile"
TRENDING = "trending"
RANGING = "ranging"
UNKNOWN = "unknown"


def classify_regime(
    candles: pd.DataFrame,
    adx_period: int = 14,
    trend_adx: float = 25.0,
    volatile_atr_pct: float = 0.02,
) -> str:
    """Devuelve el régimen actual. `volatile_atr_pct` es ATR/precio (p.ej. 0.02 = 2%);
    ajústalo al timeframe (en marcos cortos usa un valor menor)."""
    if len(candles) < adx_period * 2 + 1:
        return UNKNOWN

    high, low, close = candles["high"], candles["low"], candles["close"]
    last_price = float(close.iloc[-1])

    atr_val = float(indicators.atr(high, low, close, adx_period).iloc[-1])
    atr_pct = atr_val / last_price if last_price else 0.0
    if atr_pct >= volatile_atr_pct:
        return VOLATILE

    adx_val = float(indicators.adx(high, low, close, adx_period).iloc[-1])
    if math.isnan(adx_val):
        return UNKNOWN
    return TRENDING if adx_val >= trend_adx else RANGING


def is_btc_macro_bullish(
    exchange: any,
    symbol: str = "BTC/USDT",
    ema_period: int = 50,
    timeframe: str = "1d",
) -> bool:
    """Verifica si Bitcoin (BTC/USDT) se encuentra en tendencia macro alcista (Cierre >= EMA50 diaria).
    
    Si la consulta falla por red, devuelve True por defecto para no bloquear la operativa.
    """
    if exchange is None:
        return True
    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=ema_period + 30)
        if candles is None or len(candles) < ema_period:
            return True
        close = candles["close"]
        ema50 = float(indicators.ema(close, ema_period).iloc[-1])
        last_price = float(close.iloc[-1])
        return last_price >= ema50
    except Exception:
        return True
