#!/usr/bin/env python3
"""Resumen consolidado y visual de beneficios del bot (Spot + Carry Funding).

Uso:
    python scripts/beneficios.py               # lee la base de datos local y status.json
    python scripts/beneficios.py --gist        # consulta el último estado en vivo desde GitHub Gist
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.config import load_config
from tradebot.storage import Storage

GIST_URL = "https://gist.githubusercontent.com/AntonioCastillo/fe35efaf579e692fc11f338c60cb69f7/raw/tradebot_status.json"


def fetch_gist_status() -> dict | None:
    try:
        req = urllib.request.Request(
            f"{GIST_URL}?_nocache={int(Path(__file__).stat().st_mtime)}",
            headers={"User-Agent": "Tradebot-CLI", "Cache-Control": "no-cache"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"⚠️ No pude consultar el Gist: {e}")
        return None


def main() -> None:
    use_gist = "--gist" in sys.argv
    config = load_config()
    db_path = config.effective_db_path()

    print("\n" + "═" * 70)
    print("💰 DASHBOARD CONSOLIDADO DE BENEFICIOS — TRADEBOT (KuCoin)")
    print("═" * 70)

    if use_gist or not Path(db_path).exists():
        data = fetch_gist_status()
        if not data:
            print("❌ No se encontraron datos ni en local ni en Gist.")
            return
        
        inst = data.get("instances", {}).get("spot", {})
        ts = data.get("timestamp", "n/d")
        equity = inst.get("equity", 0.0)
        spot_pnl = inst.get("pnl_abs", 0.0)
        closed_trades = inst.get("closed_trades", 0)
        win_rate = inst.get("win_rate", 0.0) * 100
        avg_pnl = inst.get("avg_pnl_pct", 0.0)
        
        carry_info = inst.get("carry", {})
        funding_total = carry_info.get("total_funding_collected", 0.0)
        carry_positions = carry_info.get("positions", [])
        
        open_positions = inst.get("open_positions", [])
        by_head = inst.get("by_head", [])

        # Calcular P&L flotante
        floating_pnl = sum(p.get("pnl_abs", 0.0) for p in open_positions)
        total_realized = spot_pnl + funding_total
        total_net = total_realized + floating_pnl

        print(f"🕒 Fecha de actualización: {ts}")
        print(f"💎 Patrimonio Total Cuenta: {equity:,.2f} USDT\n")

        print("┌" + "─" * 68 + "┐")
        print("│ 💵 RESUMEN FINANCIERO CONSOLIDADO                                  │")
        print("├" + "─" * 68 + "┤")
        print(f"│ 1. Beneficio Realizado en Spot (Trading):  {spot_pnl:+10.2f} USDT ({closed_trades} ops, {win_rate:.1f}% WR) │")
        print(f"│ 2. Funding Pasivo Cobrado (Carry Trade):   {funding_total:+10.4f} USDT                     │")
        print(f"│ ────────────────────────────────────────────────────────────────── │")
        print(f"│ ✅ TOTAL BENEFICIO REALIZADO EN CAJA:      {total_realized:+10.2f} USDT                     │")
        print(f"│ 3. P&L Flotante (Posiciones Abiertas):     {floating_pnl:+10.2f} USDT                     │")
        print(f"│ ────────────────────────────────────────────────────────────────── │")
        print(f"│ 🚀 BENEFICIO NETO GLOBAL (Caja + Flotante):{total_net:+10.2f} USDT                     │")
        print("└" + "─" * 68 + "┘")

        # Desglose por cabeza
        if by_head:
            print("\n📊 RENDIMIENTO POR CABEZA:")
            print(f"{'Cabeza':<22} {'Trades':<8} {'Wins':<6} {'Win Rate':<10} {'P&L USDT':<12}")
            print("─" * 60)
            for h in by_head:
                t = h.get("trades", 0)
                w = h.get("wins", 0)
                wr = (w / t * 100) if t else 0
                pnl = h.get("pnl_abs", 0.0)
                print(f"{h.get('head', 'n/d'):<22} {t:<8} {w:<6} {wr:>6.1f}%   {pnl:>+9.2f} USDT")

        # Desglose Carry Trade
        if carry_positions:
            print("\n⚖️ POSICIONES CARRY TRADE (Delta-Neutral):")
            print(f"{'Símbolo':<12} {'Nocional':<14} {'Funding Cobrado':<18} {'Entrada Spot/Perp':<20}")
            print("─" * 66)
            for cp in carry_positions:
                sym = cp.get("symbol", "n/d")
                notional = cp.get("notional", 0.0)
                f_col = cp.get("funding_collected", 0.0)
                entry = cp.get("spot_entry", 0.0)
                print(f"{sym:<12} ${notional:<12.2f} {f_col:>+10.4f} USDT      @ {entry:.2f}")

        # Posiciones Abiertas
        if open_positions:
            print("\n🔓 POSICIONES SPOT EN CURSO:")
            print(f"{'Símbolo':<12} {'Cabeza':<20} {'Entrada':<10} {'Precio':<10} {'P&L Flotante':<15}")
            print("─" * 70)
            for op in open_positions:
                sym = op.get("symbol", "n/d")
                cat = op.get("category", "n/d")
                ep = op.get("entry_price", 0.0)
                cp = op.get("current_price", ep)
                pnl = op.get("pnl_abs", 0.0)
                pct = op.get("pnl_pct", 0.0)
                print(f"{sym:<12} {cat:<20} {ep:<10.4f} {cp:<10.4f} {pnl:>+6.2f} USDT ({pct:>+5.2f}%)")

    else:
        storage = Storage(db_path)
        s = storage.summary()
        print(f"📊 Base de datos local: {db_path}")
        print(f"• Trades cerrados: {s['trades']} (Win Rate: {s['win_rate']*100:.1f}%)")
        print(f"• P&L Spot realizado: {s['pnl_abs']:+.2f} {config.risk.quote_currency}")
        storage.close()

    print("\n" + "═" * 70 + "\n")


if __name__ == "__main__":
    main()
