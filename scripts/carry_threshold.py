"""¿Renta el carry SOLO cuando el funding está alto de verdad?

Barre umbrales de entrada (funding anualizado) y mide, sobre histórico real
(funding + spot + perp alineados a 8h), el neto tras comisiones y basis:
entrar cuando el funding anualizado ≥ umbral, salir cuando cae a la mitad.

Compara con la baseline "siempre dentro". Cero dinero. Público.

Uso:
    python scripts/carry_threshold.py
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ccxt  # noqa: E402
import pandas as pd  # noqa: E402

from tradebot.config import load_config  # noqa: E402
from tradebot.exchange import Exchange  # noqa: E402
from tradebot.factory import setup_logging  # noqa: E402
from tradebot.funding import simulate_threshold_carry  # noqa: E402

PAIRS = [("ETH/USDT", "ETH/USDT:USDT"), ("XRP/USDT", "XRP/USDT:USDT"),
         ("DOGE/USDT", "DOGE/USDT:USDT"), ("BTC/USDT", "BTC/USDT:USDT")]

# Umbrales de ENTRADA (funding anualizado %). 0 = siempre dentro (baseline).
THRESHOLDS = [0, 10, 20, 30, 50, 75, 100]


def _perp_close(fut, symbol, total=500):
    tf_ms = 8 * 3600 * 1000
    since = fut.milliseconds() - total * tf_ms
    raw = fut.fetch_ohlcv(symbol, "8h", since=since, limit=total)
    df = pd.DataFrame(raw, columns=["timestamp", "o", "h", "l", "close", "v"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df.set_index("timestamp")["close"]


def main() -> None:
    config = load_config()
    setup_logging("WARNING")
    exchange = Exchange(config)
    fut = ccxt.kucoinfutures({"enableRateLimit": True})
    cost = config.carry.fee_pct * 4 * 100   # 2 patas × abrir+cerrar (aprox), en %

    print("=" * 82)
    print("CARRY CON UMBRAL DE FUNDING — ¿renta solo cuando está alto de verdad?")
    print(f"velas 8h · roundtrip≈{cost:.2f}% · salida = mitad del umbral de entrada")
    print("=" * 82)

    for spot_sym, perp_sym in PAIRS:
        try:
            fh = exchange.fetch_funding_history(perp_sym, 500)
            fdf = pd.DataFrame(
                [{"timestamp": pd.to_datetime(x["timestamp"], unit="ms", utc=True),
                  "rate": x["fundingRate"]} for x in fh if x.get("fundingRate") is not None]
            ).set_index("timestamp")["rate"].sort_index()
            spot = exchange.fetch_ohlcv_history(spot_sym, "8h", 500)["close"].sort_index()
            perp = _perp_close(fut, perp_sym, 500).sort_index()
        except Exception as e:
            print(f"\n{spot_sym}: SKIP ({e})")
            continue

        spot_al = spot.reindex(fdf.index, method="ffill")
        perp_al = perp.reindex(fdf.index, method="ffill")
        df = pd.DataFrame({"rate": fdf, "spot": spot_al, "perp": perp_al}).dropna()
        if df.empty:
            print(f"\n{spot_sym}: sin datos alineados")
            continue

        f, s, p = df["rate"].tolist(), df["spot"].tolist(), df["perp"].tolist()
        days = len(df) / 3.0
        print(f"\n{spot_sym}  ({len(df)} periodos ≈ {days:.0f} días)")
        print(f"  {'entrada':>8} {'%dentro':>8} {'trips':>6} {'funding':>9} "
              f"{'basis':>8} {'coste':>7} {'NETO':>8} {'anualiz.':>9} {'fund.medio':>11}")
        for thr in THRESHOLDS:
            sim = simulate_threshold_carry(spot_sym, f, s, p,
                                           entry_pct=thr, exit_pct=thr / 2,
                                           roundtrip_cost_pct=cost)
            label = "siempre" if thr == 0 else f"≥{thr}%"
            print(f"  {label:>8} {sim.time_in_pct:>7.0f}% {sim.trips:>6} "
                  f"{sim.funding_pct:>+8.2f}% {sim.basis_pct:>+7.2f}% {sim.cost_pct:>6.2f}% "
                  f"{sim.net_pct:>+7.2f}% {sim.annualized_net_pct:>+8.1f}% "
                  f"{sim.avg_ann_in:>10.0f}%")

    print("\n" + "-" * 82)
    print("NETO = funding + basis - coste en la ventana · anualiz. = neto extrapolado a 1 año.")
    print("OJO: KuCoin limita el histórico de funding (~pocos meses); muestra corta = ruido.")


if __name__ == "__main__":
    main()
