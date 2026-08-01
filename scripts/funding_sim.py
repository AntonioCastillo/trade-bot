"""Simulador PAPER de funding-carry delta-neutral (long spot + short perp).

Alinea funding + precio spot + precio perp (velas 8h) y simula el carry con
costes y basis risk. Cero dinero. Público.

Uso:
    python scripts/funding_sim.py
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
from tradebot.funding import simulate_carry  # noqa: E402

PAIRS = [("BTC/USDT", "BTC/USDT:USDT"), ("ETH/USDT", "ETH/USDT:USDT"),
         ("XRP/USDT", "XRP/USDT:USDT"), ("DOGE/USDT", "DOGE/USDT:USDT")]


def _perp_ohlcv(fut, symbol, total=300):
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

    print("=" * 78)
    print("SIMULADOR FUNDING-CARRY delta-neutral (long spot + short perp) | velas 8h")
    print("=" * 78)
    print(f"{'símbolo':10} {'días':>5} {'funding':>9} {'basis':>8} {'coste':>7} "
          f"{'NETO':>8} {'anualiz.':>9} {'maxDD':>7}")
    print("-" * 78)

    for spot_sym, perp_sym in PAIRS:
        try:
            fh = exchange.fetch_funding_history(perp_sym, 300)
            fdf = pd.DataFrame(
                [{"timestamp": pd.to_datetime(x["timestamp"], unit="ms", utc=True),
                  "rate": x["fundingRate"]} for x in fh if x.get("fundingRate") is not None]
            ).set_index("timestamp")["rate"]
            spot = exchange.fetch_ohlcv_history(spot_sym, "8h", 300)["close"]
            perp = _perp_ohlcv(fut, perp_sym, 300)
        except Exception as e:
            print(f"{spot_sym:10} SKIP: {e}")
            continue

        # El funding liquida en instantes que no coinciden con las velas 8h;
        # alineamos cada funding al último cierre disponible (ffill).
        fdf = fdf.sort_index()
        spot_al = spot.sort_index().reindex(fdf.index, method="ffill")
        perp_al = perp.sort_index().reindex(fdf.index, method="ffill")
        df = pd.DataFrame({"rate": fdf, "spot": spot_al, "perp": perp_al}).dropna()
        if df.empty:
            print(f"{spot_sym:10} sin datos alineados")
            continue
        sim = simulate_carry(spot_sym, df["rate"].tolist(),
                             df["spot"].tolist(), df["perp"].tolist())
        print(f"{spot_sym:10} {sim.days:>5.0f} {sim.funding_pct:>+8.2f}% {sim.basis_pct:>+7.2f}% "
              f"{sim.cost_pct:>6.2f}% {sim.net_pct:>+7.2f}% {sim.annualized_pct:>+8.1f}% "
              f"{sim.max_drawdown_pct:>6.2f}%")

    print("-" * 78)
    print("funding=cobrado (recurrente) · basis=P&L divergencia spot/perp (riesgo) ·")
    print("NETO=funding+basis-coste en la ventana · anualiz.=funding extrapolado a 1 año.")


if __name__ == "__main__":
    main()
