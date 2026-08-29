"""Selección dinámica de activos por Fuerza Relativa (Relative Strength - RS vs BTC).

Mide el rendimiento de cada activo de una cesta (pool) frente al activo de referencia
(p.ej. BTC/USDT) en una ventana de N días (p.ej. 14 días). Aplica histéresis para evitar
rotaciones impulsivas si la diferencia es marginal.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_RS_POOL = [
    "SOL/USDT", "AVAX/USDT", "BNB/USDT", "ADA/USDT", "LINK/USDT",
    "LTC/USDT", "NEAR/USDT", "XRP/USDT", "DOGE/USDT", "ETH/USDT",
    "DOT/USDT", "ATOM/USDT", "UNI/USDT", "TRX/USDT", "SUI/USDT"
]


def compute_rs_rankings(
    exchange: Any,
    pool: list[str] | None = None,
    benchmark_symbol: str = "BTC/USDT",
    lookback_days: int = 14,
    timeframe: str = "1d",
) -> dict[str, float]:
    """Calcula la Fuerza Relativa (%) de cada símbolo del pool respecto a BTC/USDT.
    
    RS_symbol = Return_symbol(Nd) - Return_BTC(Nd)
    """
    pool_symbols = pool or DEFAULT_RS_POOL
    if benchmark_symbol not in pool_symbols:
        pool_symbols = list(pool_symbols) + [benchmark_symbol]

    prices_start: dict[str, float] = {}
    prices_end: dict[str, float] = {}

    for sym in pool_symbols:
        try:
            candles = exchange.fetch_ohlcv(sym, timeframe=timeframe, limit=lookback_days + 2)
            if len(candles) >= 2:
                # Usar cierres de las velas
                start_p = float(candles.iloc[0]["close"])
                end_p = float(candles.iloc[-1]["close"])
                if start_p > 0 and end_p > 0:
                    prices_start[sym] = start_p
                    prices_end[sym] = end_p
        except Exception as e:
            logger.warning("[RS] No se pudieron descargar datos de %s: %s", sym, e)

    if benchmark_symbol not in prices_start or prices_start[benchmark_symbol] <= 0:
        logger.error("[RS] No se pudo obtener precio de referencia para %s", benchmark_symbol)
        return {}

    btc_return = (prices_end[benchmark_symbol] - prices_start[benchmark_symbol]) / prices_start[benchmark_symbol]

    rankings: dict[str, float] = {}
    for sym in pool_symbols:
        if sym == benchmark_symbol:
            continue
        if sym in prices_start and prices_start[sym] > 0:
            ret = (prices_end[sym] - prices_start[sym]) / prices_start[sym]
            rs_val = (ret - btc_return) * 100.0   # en puntos porcentuales
            rankings[sym] = round(rs_val, 2)

    # Ordenar por RS descendente
    return dict(sorted(rankings.items(), key=lambda item: item[1], reverse=True))


def select_top_symbols(
    current_symbols: list[str],
    rankings: dict[str, float],
    top_k: int = 2,
    hysteresis_pct: float = 5.0,   # en puntos porcentuales (ej. 5.0 = 5%)
) -> list[str]:
    """Selecciona los Top-K símbolos con mayor RS aplicando un filtro de histéresis.
    
    Un símbolo activo actual solo se reemplaza si el nuevo candidato supera su RS
    por más de `hysteresis_pct` puntos porcentuales.
    """
    if not rankings:
        return current_symbols

    sorted_candidates = list(rankings.keys())
    if len(sorted_candidates) <= top_k:
        return sorted_candidates

    # Si no hay símbolos actuales, tomar los top_k directamente
    if not current_symbols:
        return sorted_candidates[:top_k]

    selected: list[str] = list(current_symbols[:top_k])

    # Para cada posición en los top_k, verificar si hay un candidato mejor fuera de selected
    for i in range(len(selected)):
        curr_sym = selected[i]
        curr_rs = rankings.get(curr_sym, -999.0)

        # Buscar el candidato con mayor RS que no esté ya seleccionado
        for challenger in sorted_candidates:
            if challenger in selected:
                continue
            challenger_rs = rankings.get(challenger, -999.0)

            # Si el desafiante supera al actual por más del umbral de histéresis
            if challenger_rs > curr_rs + hysteresis_pct:
                logger.info(
                    "[RS] Reemplazando %s (RS %.2f%%) por %s (RS %.2f%% > %.2f%% + %.2f%%)",
                    curr_sym, curr_rs, challenger, challenger_rs, curr_rs, hysteresis_pct
                )
                selected[i] = challenger
                break

    return selected
