"""Análisis de pairs trading (reversión del spread entre dos monedas).

Mide si, cuando el ratio A/B se desvía mucho de su media (z-score bajo = A barato
respecto a B), tiende a revertir. Reporta dos versiones:
  - spread (neutral al mercado): long A + short B → NECESITA futuros (spot no
    permite cortos). Paga 2 patas de comisión.
  - long-only: comprar solo A (el rezagado) esperando que recupere → ejecutable
    en spot, 1 pata de comisión.

Es análisis, no una cabeza del motor (requeriría operar dos símbolos a la vez).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def ratio_zscore(a_close: pd.Series, b_close: pd.Series, lookback: int):
    ratio = a_close / b_close
    mean = ratio.rolling(lookback).mean()
    std = ratio.rolling(lookback).std(ddof=0)
    z = (ratio - mean) / std
    return ratio, z


@dataclass
class PairResult:
    count: int
    mean_spread_fwd: dict[int, float]   # long A / short B (neutral)
    mean_long_fwd: dict[int, float]     # solo comprar A


def analyze_pair(
    a: pd.DataFrame,
    b: pd.DataFrame,
    lookback: int = 50,
    entry_z: float = 2.0,
    horizons: tuple[int, ...] = (1, 3, 5, 10),
) -> PairResult:
    df = pd.DataFrame({"a": a["close"], "b": b["close"]}).dropna()
    ratio, z = ratio_zscore(df["a"], df["b"], lookback)
    signal = (z <= -entry_z).fillna(False)   # A barato vs B -> esperar reversión

    means_spread: dict[int, float] = {}
    means_long: dict[int, float] = {}
    for k in horizons:
        spread_fwd = (ratio.shift(-k) / ratio - 1)[signal].dropna()
        long_fwd = (df["a"].shift(-k) / df["a"] - 1)[signal].dropna()
        means_spread[k] = float(spread_fwd.mean()) if len(spread_fwd) else 0.0
        means_long[k] = float(long_fwd.mean()) if len(long_fwd) else 0.0

    return PairResult(int(signal.sum()), means_spread, means_long)
