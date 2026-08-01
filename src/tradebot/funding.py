"""Análisis de funding-rate carry (cash-and-carry delta-neutral).

La operativa: comprar spot + cortar perpetuo (mismo tamaño). Cada 8h cobras (o
pagas) el funding rate. Al estar cubierto, el resultado ≈ suma de los funding
rates cobrados, sin exposición direccional.

Este módulo MIDE el histórico: rendimiento anualizado, % de periodos positivos y
rendimiento acumulado. Es análisis (no una cabeza del motor spot: requiere
futuros). NO es consejo.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

PERIODS_PER_YEAR = 3 * 365   # funding cada 8h -> 3 al día


@dataclass
class FundingResult:
    symbol: str
    periods: int
    days: float
    mean_rate: float           # funding medio por periodo (fracción)
    annualized_pct: float      # rendimiento anualizado del carry (bruto)
    positive_pct: float        # % de periodos con funding positivo (cobras)
    cumulative_pct: float      # rendimiento acumulado en la ventana medida


@dataclass
class CarrySim:
    symbol: str
    periods: int
    days: float
    funding_pct: float         # funding cobrado en la ventana (recurrente)
    basis_pct: float           # P&L por divergencia spot/perp (basis risk, ~0 neto)
    cost_pct: float            # coste único de montar+deshacer las dos patas
    net_pct: float             # resultado neto en la ventana
    annualized_pct: float      # rendimiento anualizado (funding recurrente)
    max_drawdown_pct: float    # peor caída de la curva (mide el basis risk)


def simulate_carry(
    symbol: str,
    funding: list[float],
    spot: list[float],
    perp: list[float],
    roundtrip_cost_pct: float = 0.30,
) -> CarrySim:
    """Simula el carry delta-neutral (long spot + short perp) periodo a periodo.

    Cada periodo cobra el funding y marca a mercado el basis (spot vs perp). Las
    listas deben venir ya alineadas por tiempo (mismo timestamp de funding)."""
    n = min(len(funding), len(spot), len(perp))
    if n == 0:
        return CarrySim(symbol, 0, 0.0, 0.0, 0.0, roundtrip_cost_pct, -roundtrip_cost_pct, 0.0, 0.0)

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    total_funding = 0.0
    total_basis = 0.0
    for i in range(n):
        f = funding[i]
        if i > 0 and spot[i - 1] and perp[i - 1]:
            basis = (spot[i] / spot[i - 1] - 1) - (perp[i] / perp[i - 1] - 1)
        else:
            basis = 0.0
        equity += f + basis
        total_funding += f
        total_basis += basis
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    days = n / 3.0
    net = equity * 100 - roundtrip_cost_pct
    annualized = (total_funding * 100) * (365 / days) if days else 0.0
    return CarrySim(
        symbol=symbol, periods=n, days=days,
        funding_pct=total_funding * 100, basis_pct=total_basis * 100,
        cost_pct=roundtrip_cost_pct, net_pct=net, annualized_pct=annualized,
        max_drawdown_pct=max_dd * 100,
    )


def analyze_funding(symbol: str, rates: list[float]) -> FundingResult:
    n = len(rates)
    if n == 0:
        return FundingResult(symbol, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
    mean = statistics.fmean(rates)
    positive = sum(1 for r in rates if r > 0) / n
    return FundingResult(
        symbol=symbol,
        periods=n,
        days=n / 3.0,
        mean_rate=mean,
        annualized_pct=mean * PERIODS_PER_YEAR * 100,
        positive_pct=positive * 100,
        cumulative_pct=sum(rates) * 100,   # carry neto acumulado (incluye periodos negativos)
    )
