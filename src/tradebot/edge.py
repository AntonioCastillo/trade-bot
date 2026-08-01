"""Edge-scanner: mide la VENTAJA BRUTA de una señal antes de construir nada.

Para cada señal candidata (una condición booleana sobre las velas) calcula el
retorno MEDIO a futuro a varios horizontes y su tasa de acierto. Si ese retorno
medio no supera el coste de ida y vuelta, la señal no tiene nada explotable —
por muy bien que ajustes TP/SL. Es la forma barata y honesta de vetar ideas.

Uso típico: `scan(candles)` devuelve un ranking; compara `best_mean` con el coste.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import indicators


def forward_return(close: pd.Series, k: int) -> pd.Series:
    """Retorno a `k` velas vista: close[i+k]/close[i] - 1."""
    return close.shift(-k) / close - 1.0


@dataclass
class EdgeResult:
    name: str
    count: int
    hit_rate: float             # % de casos con retorno positivo (horizonte ref)
    means: dict[int, float]     # retorno medio por horizonte (fracción)
    best_mean: float            # mejor retorno medio entre horizontes
    best_horizon: int

    def beats(self, cost: float) -> bool:
        return self.best_mean > cost


def candidate_signals(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Biblioteca de señales candidatas -> máscara booleana (True donde dispara)."""
    o, close = df["open"], df["close"]
    vol = df["volume"]
    rsi = indicators.rsi(close, 14)
    bb = indicators.bollinger_bands(close, 20, 2.0)
    fast = close.ewm(span=9, adjust=False).mean()
    slow = close.ewm(span=21, adjust=False).mean()
    body = (close - o) / o
    green = close > o

    hour = pd.Series(close.index.hour, index=close.index) if hasattr(close.index, "hour") else None
    bb_width = (bb["upper"] - bb["lower"]) / bb["middle"]
    signals = {
        "baseline (todas)":     pd.Series(True, index=close.index),
        "vela verde":           green,
        "verde fuerte >0.2%":   green & (body >= 0.002),
        "2 verdes seguidas":    green & green.shift(1).fillna(False),
        "RSI<30 sobreventa":    rsi < 30,
        "RSI<25 muy sobrevendido": rsi < 25,
        "RSI>70 sobrecompra":   rsi > 70,
        "RSI>80 muy sobrecomprado": rsi > 80,
        "toca banda inferior":  close <= bb["lower"],
        "toca banda superior":  close >= bb["upper"],
        "volumen x2":           vol >= vol.rolling(20).mean() * 2,
        "volumen x3":           vol >= vol.rolling(20).mean() * 3,
        "breakout max20":       close > close.rolling(20).max().shift(1),
        "breakout max55":       close > close.rolling(55).max().shift(1),
        "cruce EMA9>21":        (fast.shift(1) <= slow.shift(1)) & (fast > slow),
        "squeeze (vol baja)":   bb_width <= bb_width.rolling(50).quantile(0.2),
    }
    if hour is not None:
        # Efecto sesión: apertura EE.UU. (~13-16h UTC) y asiática (~0-3h UTC).
        signals["sesión US (13-16 UTC)"] = hour.between(13, 16)
        signals["sesión Asia (0-3 UTC)"] = hour.between(0, 3)
    return signals


def evaluate_signal(
    close: pd.Series, mask: pd.Series, horizons: tuple[int, ...], ref_horizon: int
) -> tuple[int, float, dict[int, float]]:
    mask = mask.fillna(False)
    n = int(mask.sum())
    means: dict[int, float] = {}
    for k in horizons:
        fr = forward_return(close, k)[mask].dropna()
        means[k] = float(fr.mean()) if len(fr) else 0.0
    fr_ref = forward_return(close, ref_horizon)[mask].dropna()
    hit = float((fr_ref > 0).mean()) if len(fr_ref) else 0.0
    return n, hit, means


def scan(
    df: pd.DataFrame,
    signals: dict[str, pd.Series] | None = None,
    horizons: tuple[int, ...] = (1, 3, 5, 10),
    ref_horizon: int = 3,
) -> list[EdgeResult]:
    """Evalúa todas las señales y devuelve un ranking por mejor retorno medio."""
    signals = signals if signals is not None else candidate_signals(df)
    close = df["close"]
    results: list[EdgeResult] = []
    for name, mask in signals.items():
        n, hit, means = evaluate_signal(close, mask, horizons, ref_horizon)
        if n == 0:
            continue
        best_h = max(means, key=lambda k: means[k])
        results.append(EdgeResult(name, n, hit, means, means[best_h], best_h))
    results.sort(key=lambda r: r.best_mean, reverse=True)
    return results
