"""Indicadores técnicos. Implementación propia sobre pandas para evitar
depender de ta-lib (que necesita compilación nativa en Windows)."""

from __future__ import annotations

import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI de Wilder. Devuelve una serie 0-100; NaN hasta tener `period` datos."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Media móvil exponencial estilo Wilder (alpha = 1/period).
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    result = 100 - (100 / (1 + rs))
    # Si no hay pérdidas, RSI = 100; si no hay ganancias, RSI = 0.
    result = result.where(avg_loss != 0, 100.0)
    result = result.where(avg_gain != 0, result.where(avg_loss == 0, 0.0))
    return result


def atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Average True Range (Wilder). Mide la volatilidad en unidades de precio."""
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Average Directional Index (Wilder). Mide la FUERZA de la tendencia (no la
    dirección): ADX alto (>25) = mercado con tendencia; bajo (<20) = lateral."""
    up = high.diff()
    down = -low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)

    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)

    alpha = 1 / period
    atr = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr
    di_sum = (plus_di + minus_di).replace(0.0, float("nan"))
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    return dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()


def bollinger_bands(
    close: pd.Series, period: int = 20, num_std: float = 2.0
) -> pd.DataFrame:
    """Bandas de Bollinger. Columnas: lower, middle (SMA), upper."""
    middle = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    return pd.DataFrame(
        {
            "lower": middle - num_std * std,
            "middle": middle,
            "upper": middle + num_std * std,
        }
    )
