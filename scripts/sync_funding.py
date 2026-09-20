#!/usr/bin/env python3
"""Sincronizador del historial de pagos de funding desde KuCoin Futuros a SQLite.

Consulta todos los devengos históricos (ETH, SOL, etc.) directamente desde la API
privada de KuCoin Futuros y los vuelca en la tabla `funding_payments` de SQLite
de forma idempotente (sin duplicados).

Uso:
    python scripts/sync_funding.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.config import load_config
from tradebot.execution.futures import FuturesBroker
from tradebot.storage import Storage


def main() -> None:
    config = load_config()
    db_path = config.effective_db_path()
    storage = Storage(db_path)

    print("\n" + "═" * 70)
    print("🔄 SINCRONIZACIÓN DE HISTORIAL DE FUNDING (KuCoin Futuros -> SQLite)")
    print("═" * 70)
    print(f"📁 Base de datos destino: {db_path}")

    if not config.credentials.is_complete:
        print("❌ Credenciales de KuCoin no configuradas en el entorno (.env).")
        return

    broker = FuturesBroker(config, leverage=1.0, dry_run=False)
    print("📡 Consultando historial de devengos en KuCoin Futuros...")

    records = broker.fetch_historical_funding_records()
    if not records:
        print("⚠️ No se encontraron registros de funding en KuCoin o no hubo respuesta.")
        return

    print(f"📥 Se encontraron {len(records)} registros históricos de funding en KuCoin.")

    inserted = 0
    for r in records:
        storage.record_funding_payment(
            timestamp=r["timestamp"],
            symbol=r["symbol"],
            rate=r["rate"],
            amount_usdt=r["amount_usdt"],
            notional=r["notional"],
            payment_id=r["id"],
        )
        inserted += 1

    total_funding = storage.total_funding_collected()
    all_payments = storage.all_funding_payments()

    print(f"✅ Sincronización completada: {len(all_payments)} pagos registrados en SQLite.")
    print(f"💰 Total Funding Histórico Acumulado: {total_funding:+.6f} USDT")

    print("\n📋 ÚLTIMOS 15 DEVENGOS HISTÓRICOS:")
    print(f"{'Fecha (UTC)':<20} {'Símbolo':<12} {'Tasa 8h':<10} {'Cobrado':<14} {'Nocional':<12}")
    print("─" * 70)
    for p in all_payments[:15]:
        ts = p["timestamp"][:19].replace("T", " ")
        sym = p["symbol"]
        rate_pct = float(p["rate"]) * 100
        amt = float(p["amount_usdt"])
        notional = float(p["notional"])
        print(f"{ts:<20} {sym:<12} {rate_pct:>+6.4f}%   {amt:>+9.4f} USDT   ${notional:<8.2f}")

    storage.close()
    print("\n" + "═" * 70 + "\n")


if __name__ == "__main__":
    main()
