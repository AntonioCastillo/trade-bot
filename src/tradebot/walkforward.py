"""Validación walk-forward / out-of-sample.

El objetivo es detectar SOBREAJUSTE (curve-fitting): parámetros que brillan en
el pasado observado pero fallan en datos nuevos.

Método (walk-forward anclado):
  - Se divide el histórico en un tramo de entrenamiento inicial y N bloques OOS.
  - En cada paso, el tramo de entrenamiento (in-sample, IS) crece e incluye todo
    lo anterior; sobre él se elige la mejor combinación de parámetros de una
    rejilla (grid search).
  - Esos parámetros se aplican al bloque siguiente, NUNCA visto (out-of-sample,
    OOS), y se miden sus resultados.
  - Se agregan todos los tramos OOS: eso es la estimación honesta de rendimiento
    futuro. Si IS >> OOS de forma sistemática, hay sobreajuste.

Si `param_grid` es None, no se optimiza: se usan los parámetros actuales tal
cual, comparando IS vs OOS (test de consistencia puro).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import pandas as pd

from .backtester import run_backtest
from .config import Config, Instrument
from .metrics import Metrics, compute_metrics
from .strategy import build_strategy

# Rejillas por defecto (modestas para acotar el tiempo de cómputo).
DEFAULT_GRIDS: dict[str, dict[str, list]] = {
    "mean_reversion": {
        "rsi_oversold": [25, 30, 35],
        "bb_std": [1.5, 2.0, 2.5],
    },
    "momentum": {
        "breakout_atr_mult": [0.3, 0.5, 1.0],
        "volume_mult": [1.0, 1.2, 1.5],
    },
    "volume_surge": {
        "surge_mult": [2.0, 2.5, 3.5],
        "min_change_pct": [0.0, 0.005, 0.01],
    },
    "grid": {
        "range_period": [60, 100, 150],
        "levels": [8, 12, 20],
    },
    "scalping": {
        "ema_fast": [3, 5, 8],
        "ema_slow": [13, 20, 30],
    },
    "breakout": {
        "lookback": [10, 20, 55],
    },
    "trend": {
        "fast": [10, 20, 50],
        "slow": [50, 100, 200],
    },
}


@dataclass
class Fold:
    index: int
    train_size: int
    test_size: int
    best_params: dict
    is_metrics: Metrics
    oos_metrics: Metrics


@dataclass
class WalkForwardResult:
    symbol: str
    strategy: str
    folds: list[Fold]
    is_metrics: Metrics     # agregado de todos los tramos IS (con params elegidos)
    oos_metrics: Metrics    # agregado de todos los tramos OOS -> lo que importa


def _param_combos(grid: dict[str, list]) -> list[dict]:
    keys = list(grid.keys())
    return [dict(zip(keys, values)) for values in itertools.product(*grid.values())]


def _evaluate(candles, strategy_name, params, instrument, config, warmup=None):
    strategy = build_strategy(strategy_name, params)
    result = run_backtest(candles, strategy, instrument, config, warmup=warmup)
    metrics = compute_metrics(result.trades, result.starting_balance)
    return metrics, result.trades


def _grid_search(candles, strategy_name, instrument, config, grid, min_trades):
    base = instrument.strategy_params
    best_params = dict(base)
    best_metrics = None
    best_obj = float("-inf")

    for override in _param_combos(grid):
        params = {**base, **override}
        metrics, _ = _evaluate(candles, strategy_name, params, instrument, config)
        # Objetivo: rentabilidad, exigiendo un mínimo de operaciones para que
        # no gane una config que simplemente no opera.
        obj = metrics.return_pct if metrics.trades >= min_trades else float("-inf")
        if obj > best_obj:
            best_obj, best_metrics, best_params = obj, metrics, params

    if best_metrics is None:  # ninguna combinación alcanzó min_trades
        best_params = dict(base)
        best_metrics, _ = _evaluate(candles, strategy_name, best_params, instrument, config)
    return best_params, best_metrics


def walk_forward(
    candles: pd.DataFrame,
    instrument: Instrument,
    config: Config,
    n_splits: int = 3,
    initial_train_ratio: float = 0.5,
    param_grid: dict[str, list] | None = None,
    min_trades: int = 3,
) -> WalkForwardResult:
    strategy_name = instrument.strategy_name
    lookback = config.lookback
    total = len(candles)
    initial_train = int(total * initial_train_ratio)
    oos_size = max(1, (total - initial_train) // n_splits)

    folds: list[Fold] = []
    all_is_trades: list = []
    all_oos_trades: list = []

    for i in range(n_splits):
        train_end = initial_train + i * oos_size
        test_end = total if i == n_splits - 1 else train_end + oos_size
        if train_end >= total or test_end <= train_end:
            break

        train = candles.iloc[:train_end]
        # Contexto previo para que los indicadores lleguen "calientes" al OOS.
        ctx_start = max(0, train_end - lookback)
        test = candles.iloc[ctx_start:test_end]
        test_warmup = train_end - ctx_start

        if param_grid:
            best_params, is_metrics = _grid_search(
                train, strategy_name, instrument, config, param_grid, min_trades
            )
        else:
            best_params = dict(instrument.strategy_params)
            is_metrics, is_trades = _evaluate(train, strategy_name, best_params, instrument, config)
            all_is_trades.extend(is_trades)

        oos_metrics, oos_trades = _evaluate(
            test, strategy_name, best_params, instrument, config, warmup=test_warmup
        )
        all_oos_trades.extend(oos_trades)
        if param_grid:
            _, is_trades = _evaluate(train, strategy_name, best_params, instrument, config)
            all_is_trades.extend(is_trades)

        folds.append(Fold(
            index=i, train_size=train_end, test_size=test_end - train_end,
            best_params={k: best_params.get(k) for k in (param_grid or {})},
            is_metrics=is_metrics, oos_metrics=oos_metrics,
        ))

    start = config.risk.starting_balance
    return WalkForwardResult(
        symbol=instrument.symbol,
        strategy=strategy_name,
        folds=folds,
        is_metrics=compute_metrics(all_is_trades, start),
        oos_metrics=compute_metrics(all_oos_trades, start),
    )
