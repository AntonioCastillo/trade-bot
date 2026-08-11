"""A/B del filtro de régimen: corre cada cabeza CON el gate y SIN él, al
timeframe propio de la cabeza, y compara. Sirve para comprobar si apagar cada
estrategia en su régimen malo mejora (o no) el resultado out-of-sample honesto.

Uso:
    python scripts/regime_ab.py           # 2000 velas/símbolo
    python scripts/regime_ab.py 3000      # nº de velas por símbolo (paginado)
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.backtester import run_backtest  # noqa: E402
from tradebot.config import load_config  # noqa: E402
from tradebot.exchange import Exchange  # noqa: E402
from tradebot.factory import setup_logging  # noqa: E402
from tradebot.metrics import compute_metrics  # noqa: E402
from tradebot.strategy import build_strategy  # noqa: E402


def _run(candles, ins, config):
    strat = build_strategy(ins.strategy_name, ins.strategy_params)
    res = run_backtest(candles, strat, ins, config)
    return compute_metrics(res.trades, res.starting_balance)


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    config = load_config()
    setup_logging("WARNING")
    exchange = Exchange(config)

    print("=" * 82)
    print(f"A/B FILTRO DE RÉGIMEN  |  {limit} velas/símbolo  |  backtest mark-to-market")
    print("=" * 82)
    print(f"{'cabeza/símbolo':22} {'variante':16} {'ops':>4} {'ret%':>8} {'PF':>6} {'maxDD%':>7}")
    print("-" * 82)

    for ins in config.instruments:
        if not ins.regimes:
            continue  # esta cabeza no usa filtro de régimen; nada que comparar
        try:
            candles = exchange.fetch_ohlcv_history(ins.symbol, ins.timeframe, limit)
        except Exception as e:
            print(f"{ins.category+'/'+ins.symbol:22} SKIP: {e}")
            continue

        con = _run(candles, ins, config)                      # con gate
        sin = _run(candles, replace(ins, regimes=[]), config)  # sin gate

        label = f"{ins.category}/{ins.symbol}"
        for name, m in ((f"CON {ins.regimes}", con), ("SIN filtro", sin)):
            pf = "inf" if m.profit_factor == float("inf") else f"{m.profit_factor:.2f}"
            print(f"{label:22} {name:16} {m.trades:>4} {m.return_pct:>+8.2f} "
                  f"{pf:>6} {m.max_drawdown_pct:>7.2f}")
            label = ""  # solo etiquetar la primera fila del par
        print("-" * 82)

    print("\nLee: si CON el filtro cae mucho el nº de ops pero mejora ret%/PF/maxDD,")
    print("el gate está evitando entradas malas. Si empeora, la cabeza operaba mejor")
    print("sin filtro (o el régimen 'bueno' elegido no es el suyo).")


if __name__ == "__main__":
    main()
