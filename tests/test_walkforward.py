import numpy as np
import pandas as pd
from conftest import make_config, make_instrument

from tradebot.metrics import Metrics
from tradebot.walkforward import DEFAULT_GRIDS, _param_combos, walk_forward


def _oscillating(n=300):
    """Serie con dips y picos periódicos que generan operaciones repetidas."""
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    base = np.full(n, 100.0)
    for i in range(0, n, 40):
        base[i] = 78.0            # dip -> sobreventa
        if i + 20 < n:
            base[i + 20] = 122.0  # pico -> sobrecompra
    close = pd.Series(base, index=idx)
    return pd.DataFrame({
        "open": close, "high": close * 1.001, "low": close * 0.999,
        "close": close, "volume": np.full(n, 100.0),
    }, index=idx)


def test_param_combos_count():
    grid = {"a": [1, 2, 3], "b": [10, 20]}
    combos = _param_combos(grid)
    assert len(combos) == 6
    assert {"a": 1, "b": 10} in combos


def test_walk_forward_structure_without_grid():
    ins = make_instrument(symbol="BTC/USDT", strategy_name="mean_reversion")
    config = make_config(ins)
    config.lookback = 120
    res = walk_forward(_oscillating(), ins, config, n_splits=3, param_grid=None)

    assert 1 <= len(res.folds) <= 3
    for fold in res.folds:
        assert isinstance(fold.is_metrics, Metrics)
        assert isinstance(fold.oos_metrics, Metrics)
    assert isinstance(res.oos_metrics, Metrics)


def test_walk_forward_with_grid_selects_params():
    ins = make_instrument(symbol="BTC/USDT", strategy_name="mean_reversion")
    config = make_config(ins)
    config.lookback = 120
    grid = DEFAULT_GRIDS["mean_reversion"]
    res = walk_forward(_oscillating(), ins, config, n_splits=2, param_grid=grid)

    assert len(res.folds) >= 1
    for fold in res.folds:
        # Cada fold reporta los parámetros elegidos de la rejilla.
        assert set(fold.best_params.keys()) == set(grid.keys())
