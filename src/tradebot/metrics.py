"""Métricas de robustez para evaluar una estrategia más allá del P&L bruto.

Se calculan sobre la secuencia de operaciones cerradas (round-trips):
  - return_pct:       rentabilidad total sobre el capital inicial.
  - win_rate:         % de operaciones ganadoras.
  - profit_factor:    beneficio bruto / pérdida bruta (>1 es rentable).
  - max_drawdown_pct: mayor caída pico-valle de la curva de capital.
  - sharpe:           rentabilidad ajustada al riesgo (por operación).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass


@dataclass
class Metrics:
    trades: int
    wins: int
    win_rate: float
    total_pnl: float
    return_pct: float
    avg_pnl_pct: float
    profit_factor: float        # inf si no hay operaciones perdedoras
    max_drawdown_pct: float
    sharpe: float               # por operación (mean/std de los retornos)

    def format_line(self) -> str:
        pf = "inf" if math.isinf(self.profit_factor) else f"{self.profit_factor:.2f}"
        return (
            f"ops={self.trades} win={self.win_rate * 100:.0f}% "
            f"ret={self.return_pct:+.2f}% PF={pf} "
            f"maxDD={self.max_drawdown_pct:.2f}% Sharpe={self.sharpe:.2f}"
        )


def metrics_from_pnls(
    pnl_abs: list[float], pnl_pct: list[float], starting_balance: float
) -> Metrics:
    n = len(pnl_abs)
    if n == 0:
        return Metrics(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    wins = sum(1 for p in pnl_abs if p > 0)
    total = sum(pnl_abs)
    gains = sum(p for p in pnl_abs if p > 0)
    losses = -sum(p for p in pnl_abs if p < 0)
    profit_factor = (gains / losses) if losses > 0 else math.inf

    # Curva de capital y máximo drawdown.
    equity = starting_balance
    peak = equity
    max_dd = 0.0
    for p in pnl_abs:
        equity += p
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)

    # Sharpe por operación: media/desviación de los retornos por operación.
    if n >= 2:
        mean = statistics.fmean(pnl_pct)
        sd = statistics.pstdev(pnl_pct)
        sharpe = (mean / sd) if sd > 0 else 0.0
    else:
        sharpe = 0.0

    return Metrics(
        trades=n,
        wins=wins,
        win_rate=wins / n,
        total_pnl=total,
        return_pct=total / starting_balance * 100 if starting_balance else 0.0,
        avg_pnl_pct=statistics.fmean(pnl_pct),
        profit_factor=profit_factor,
        max_drawdown_pct=max_dd * 100,
        sharpe=sharpe,
    )


def compute_metrics(trades, starting_balance: float) -> Metrics:
    """`trades`: iterable de objetos con atributos `pnl_abs` y `pnl_pct`."""
    pnl_abs = [t.pnl_abs for t in trades]
    pnl_pct = [t.pnl_pct for t in trades]
    return metrics_from_pnls(pnl_abs, pnl_pct, starting_balance)
