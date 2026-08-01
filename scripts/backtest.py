"""Backtesting de TODO el universo sobre datos históricos.

Corre cada símbolo de forma independiente (misma estrategia y riesgo que en
real) y persiste cada operación cerrada en data/backtest.db. Al terminar imprime
el informe de viabilidad. Consulta luego con: python scripts/report.py data/backtest.db

Uso:
    python scripts/backtest.py            # descarga histórico de KuCoin
    python scripts/backtest.py 1000       # nº de velas por símbolo (por defecto 1000)
"""

from __future__ import annotations

import sys
from pathlib import Path

try:  # que los acentos se vean bien en la consola de Windows
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.config import load_config  # noqa: E402
from tradebot.engine import Engine  # noqa: E402
from tradebot.exchange import Exchange  # noqa: E402
from tradebot.execution.paper import PaperExecutionEngine  # noqa: E402
from tradebot.factory import build_strategies, setup_logging  # noqa: E402
from tradebot.reporting import render_report  # noqa: E402
from tradebot.risk import RiskManager  # noqa: E402
from tradebot.storage import Storage  # noqa: E402

DB_PATH = "data/backtest.db"


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    config = load_config()
    config.mode = "paper"
    setup_logging("WARNING")

    # Empezar de cero para que el informe refleje solo esta ejecución.
    db = Path(DB_PATH)
    if db.exists():
        db.unlink()
    storage = Storage(DB_PATH)

    exchange = Exchange(config)
    strategies = build_strategies(config)

    for ins in config.instruments:
        symbol = ins.symbol
        try:
            candles = exchange.fetch_ohlcv(symbol, config.timeframe, limit=limit)
        except Exception as e:
            print(f"[SKIP] {symbol}: no se pudieron descargar datos ({e})")
            continue

        # Cada símbolo con su propio balance simulado y sin cortafuegos diario.
        execution = PaperExecutionEngine(config)
        risk = RiskManager(config.risk)
        engine = Engine(
            config, strategies={symbol: strategies[symbol]}, risk=risk,
            execution=execution, storage=storage, enforce_daily_loss=False,
        )
        warmup = strategies[symbol].min_candles
        for i in range(warmup, len(candles) + 1):
            engine.process(symbol, candles.iloc[:i])

        print(f"[OK] {symbol}: {len(candles)} velas procesadas")

    print()
    print(render_report(storage, quote=config.risk.quote_currency,
                        starting_balance=config.risk.starting_balance))
    storage.close()


if __name__ == "__main__":
    main()
