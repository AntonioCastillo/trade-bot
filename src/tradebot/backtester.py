"""Backtester reutilizable: corre UNA estrategia sobre un tramo de velas y
devuelve las operaciones cerradas. Replica exactamente el comportamiento del
bot en vivo (misma ventana `lookback` por decisión), para que los resultados
del backtest sean representativos.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd

from .config import Config, Instrument
from .engine import Engine
from .execution.paper import PaperExecutionEngine
from .models import ClosedTrade, Order, Side
from .risk import RiskManager
from .storage import Storage
from .strategy.base import Strategy


@dataclass
class BacktestResult:
    trades: list[ClosedTrade]
    final_equity: float
    starting_balance: float


def run_backtest(
    candles: pd.DataFrame,
    strategy: Strategy,
    instrument: Instrument,
    config: Config,
    lookback: int | None = None,
    warmup: int | None = None,
    mark_to_market: bool = True,
    max_hold_bars: int = 0,
) -> BacktestResult:
    """Simula la estrategia sobre `candles`. `warmup` = nº de velas iniciales que
    solo sirven de contexto (no se toman decisiones); por defecto min_candles.

    `mark_to_market`: al terminar, cierra las posiciones que sigan abiertas al
    último precio y las cuenta como operaciones. Es CRÍTICO para no engañarse:
    sin esto, una estrategia que deja perdedoras abiertas (p.ej. grid) parece
    rentable porque solo se miden las ganadoras cerradas."""
    lookback = lookback or config.lookback
    warmup = warmup if warmup is not None else strategy.min_candles
    warmup = max(warmup, strategy.min_candles)

    cfg = replace(config, instruments=[instrument])
    execution = PaperExecutionEngine(cfg)
    risk = RiskManager(cfg.risk)
    storage = Storage(":memory:")
    engine = Engine(
        cfg, strategies={instrument.symbol: strategy}, risk=risk,
        execution=execution, storage=storage, enforce_daily_loss=False,
        max_hold_bars=max_hold_bars,
    )

    for i in range(warmup, len(candles) + 1):
        window = candles.iloc[max(0, i - lookback):i]
        engine.process(instrument.symbol, window)

    final_price = float(candles["close"].iloc[-1])

    if mark_to_market:
        # Cierra a mercado (al último precio) lo que quede abierto, para que las
        # métricas reflejen la verdad, no solo las ganadoras cerradas.
        for pos in list(engine.positions):
            close_side = Side.SELL if pos.side is Side.BUY else Side.BUY
            order = Order(pos.symbol, close_side, pos.amount, final_price,
                          reason="mark-to-market")
            engine._close_position(pos, order)
        engine.positions.clear()

    result = BacktestResult(
        trades=list(engine.closed_trades),
        final_equity=engine.equity(),
        starting_balance=cfg.risk.starting_balance,
    )
    storage.close()
    return result
