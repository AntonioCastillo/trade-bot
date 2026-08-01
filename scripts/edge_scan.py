"""Escanea la ventaja bruta de señales candidatas sobre datos reales de KuCoin.

Uso:
    python scripts/edge_scan.py                 # timeframe de config, 5000 velas
    python scripts/edge_scan.py 1m 8000         # timeframe y nº de velas

Para cada símbolo del universo, mide el retorno medio a futuro de cada señal y
lo compara con el coste de ida y vuelta. Una señal solo es prometedora si su
retorno medio supera claramente el coste (✓).
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.config import load_config  # noqa: E402
from tradebot.edge import scan  # noqa: E402
from tradebot.exchange import Exchange  # noqa: E402
from tradebot.factory import setup_logging  # noqa: E402

HORIZONS = (1, 3, 5, 10)


def main() -> None:
    config = load_config()
    timeframe = sys.argv[1] if len(sys.argv) > 1 else config.timeframe
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    setup_logging("WARNING")
    exchange = Exchange(config)

    cost = (config.engine.fee_pct * 2 + config.engine.slippage_pct * 2) * 100
    print("=" * 84)
    print(f"EDGE-SCANNER | {timeframe} | {limit} velas | coste ida/vuelta = {cost:.3f}%")
    print("Retorno MEDIO a futuro (%). Prometedora solo si supera el coste (✓).")
    print("=" * 84)

    for symbol in config.symbols():
        try:
            df = exchange.fetch_ohlcv_history(symbol, timeframe, limit)
        except Exception as e:
            print(f"\n{symbol}: SKIP ({e})")
            continue
        results = scan(df, horizons=HORIZONS)
        print(f"\n{symbol}")
        print(f"  {'señal':22} {'n':>6} {'hit%':>6} " +
              " ".join(f"m{k}".rjust(8) for k in HORIZONS) + f" {'mejor':>8}  edge")
        for r in results:
            row = " ".join(f"{r.means[k] * 100:>+8.3f}" for k in HORIZONS)
            mark = "✓" if r.best_mean * 100 > cost else "·"
            print(f"  {r.name:22} {r.count:>6} {r.hit_rate * 100:>5.1f}% {row} "
                  f"{r.best_mean * 100:>+8.3f}  {mark}")

    print(f"\nSolo son prometedoras las señales con 'mejor' > {cost:.3f}% (coste). "
          "El resto, aunque acierte mucho, no paga las comisiones.")


if __name__ == "__main__":
    main()
