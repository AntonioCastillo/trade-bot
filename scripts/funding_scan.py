"""Mide el funding-rate carry histórico de varios perpetuos de KuCoin.

Uso:
    python scripts/funding_scan.py            # ~1 año (1095 periodos de 8h)
    python scripts/funding_scan.py 2190       # nº de periodos

Reporta el rendimiento anualizado del carry delta-neutral (long spot + short
perp), % de periodos positivos y acumulado. Público, no opera.
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
from tradebot.exchange import Exchange  # noqa: E402
from tradebot.factory import setup_logging  # noqa: E402
from tradebot.funding import analyze_funding  # noqa: E402

# Coste una sola vez de montar+deshacer las dos patas (spot + perp), aprox.
ONE_TIME_COST_PCT = 0.30

PERPS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "XRP/USDT:USDT",
         "SOL/USDT:USDT", "DOGE/USDT:USDT"]


def main() -> None:
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 1095
    config = load_config()
    setup_logging("WARNING")
    exchange = Exchange(config)

    print("=" * 74)
    print(f"FUNDING-RATE CARRY (delta-neutral: long spot + short perp) | ~{total//3} días")
    print("Rendimiento del carry SIN riesgo direccional. Coste montaje único ≈ 0.30%.")
    print("=" * 74)
    print(f"{'perp':16} {'periodos':>8} {'días':>6} {'anualizado':>11} {'%pos':>6} {'acumulado':>10}")
    print("-" * 74)

    for sym in PERPS:
        try:
            hist = exchange.fetch_funding_history(sym, total)
        except Exception as e:
            print(f"{sym:16} SKIP: {e}")
            continue
        rates = [h["fundingRate"] for h in hist if h.get("fundingRate") is not None]
        r = analyze_funding(sym, rates)
        print(f"{sym:16} {r.periods:>8} {r.days:>6.0f} {r.annualized_pct:>+10.2f}% "
              f"{r.positive_pct:>5.0f}% {r.cumulative_pct:>+9.2f}%")

    print("-" * 74)
    print("Anualizado = rendimiento del carry si el funding se mantuviera; %pos = veces")
    print("que cobras. Ojo: es BRUTO, delta-neutral, y requiere futuros + gestión de")
    print("margen (riesgo de liquidación en la pata corta). El funding puede volverse")
    print("negativo (entonces pagas).")


if __name__ == "__main__":
    main()
