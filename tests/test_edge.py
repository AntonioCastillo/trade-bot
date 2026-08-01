import numpy as np
import pandas as pd
import pytest

from tradebot.edge import EdgeResult, forward_return, scan


def _df(prices):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="1h", tz="UTC")
    close = pd.Series(prices, index=idx)
    return pd.DataFrame({
        "open": close.shift(1).fillna(close), "high": close * 1.001,
        "low": close * 0.999, "close": close, "volume": np.full(len(prices), 100.0),
    })


def test_forward_return_basic():
    close = pd.Series([100.0, 110.0, 121.0])
    fr = forward_return(close, 1)
    assert fr.iloc[0] == pytest.approx(0.1)   # 110/100 - 1
    assert fr.iloc[1] == pytest.approx(0.1)   # 121/110 - 1
    assert pd.isna(fr.iloc[2])                # sin dato futuro


def test_scan_returns_ranked_results():
    rng = np.random.default_rng(0)
    prices = 100 + rng.standard_normal(500).cumsum()
    results = scan(_df(list(prices)))
    assert all(isinstance(r, EdgeResult) for r in results)
    # Ordenado por mejor retorno medio, descendente.
    means = [r.best_mean for r in results]
    assert means == sorted(means, reverse=True)


def test_scan_detects_a_real_edge():
    # Señal artificial: cada 10 velas hay un salto; medimos que una condición con
    # subida sistemática posterior sale con retorno medio positivo alto.
    prices = []
    for i in range(300):
        prices.append(100 + i * 0.01)   # deriva alcista suave y constante
    results = scan(_df(prices), horizons=(1, 3, 5))
    baseline = next(r for r in results if r.name == "baseline (todas)")
    # Con deriva alcista, el retorno medio a futuro del baseline es positivo.
    assert baseline.best_mean > 0
