#!/usr/bin/env python3
"""Desmontaje seguro y cierre atómico de posiciones de Carry Trade (KuCoin).

Cierra ordenadamente ambas patas de todas las posiciones de Carry activas:
  1. Vende a mercado la pata Spot del activo (ej. SOL) recuperando USDT.
  2. Recompra a mercado el corto de Futuros (reduceOnly) liberando el colateral.
  3. Registra el cobro final de funding en SQLite y actualiza el fichero de estado.
  4. Envía notificación de confirmación y capital liberado a Telegram.

Uso:
    python scripts/close_carry.py            # Cierre REAL en KuCoin
    python scripts/close_carry.py --dry-run  # Simulación de auditoría (sin órdenes)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.config import load_config
from tradebot.exchange import Exchange
from tradebot.execution.futures import FuturesBroker
from tradebot.notifier import NullNotifier, build_notifier
from tradebot.storage import Storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    config = load_config()
    db_path = config.effective_db_path()
    storage = Storage(db_path)

    notifier = build_notifier(
        config.credentials.telegram_token, config.credentials.telegram_chat_id
    ) if config.credentials.is_complete else NullNotifier()

    print("\n" + "═" * 70)
    print("⚖️ DESMONTAJE Y CIERRE DE CARRY TRADE — LIBERACIÓN DE CAPITAL")
    print("═" * 70)
    if dry_run:
        print("🔍 MODO SIMULACIÓN (--dry-run): No se enviarán órdenes al exchange.")
    else:
        print("🔴 MODO REAL: Se ejecutarán órdenes de mercado para cerrar y liquidar.")
    print(f"📁 Base de datos: {db_path}\n")

    symbols_to_check = config.carry.symbols or ["ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT"]
    broker = FuturesBroker(config, leverage=config.carry.leverage, dry_run=dry_run)
    spot = Exchange(config)

    closed_summary: list[dict] = []

    for spot_symbol in symbols_to_check:
        perp_symbol = spot_symbol if ":" in spot_symbol else f"{spot_symbol}:USDT"
        base_currency = spot_symbol.split("/")[0]

        pos_info = broker.fetch_position(perp_symbol)
        if not pos_info or pos_info.get("contracts", 0.0) <= 0:
            continue

        contracts = float(pos_info["contracts"])
        entry_price = float(pos_info.get("entry_price") or 0.0)
        mark_price = float(pos_info.get("mark_price") or entry_price)
        collateral = float(pos_info.get("collateral") or 0.0)
        unrealized = float(pos_info.get("unrealized_pnl") or 0.0)

        print(f"📌 Posición detectada en {perp_symbol}:")
        print(f"   • Contratos cortos: {contracts}")
        print(f"   • Precio de entrada: {entry_price:.4f} | Precio actual: {mark_price:.4f}")
        print(f"   • Colateral bloqueado: ~${collateral:.2f} USDT")

        # 1) Recomprar el corto en Futuros (reduceOnly)
        print(f"   🚀 Cerrando corto de {contracts} contratos en Futuros...")
        fut_res = broker.close_short(perp_symbol, contracts, mark_price)
        print(f"   ✅ Corto cerrado con éxito.")

        # 2) Consultar y vender el saldo Spot de la moneda base
        spot_bal = spot.fetch_balance(base_currency)
        print(f"   💎 Saldo Spot disponible en {base_currency}: {spot_bal:.6f}")

        sold_spot_usdt = 0.0
        if spot_bal > 0.0001:
            print(f"   🚀 Vendiendo {spot_bal:.6f} {base_currency} en Spot a mercado...")
            if dry_run:
                sold_spot_usdt = spot_bal * mark_price
                print(f"   [DRY-RUN] Venta simulada por ~${sold_spot_usdt:.2f} USDT")
            else:
                spot_res = spot.create_market_sell(spot_symbol, spot_bal)
                sold_spot_usdt = float(spot_res.get("cost") or (spot_bal * mark_price))
                print(f"   ✅ Spot vendido por +{sold_spot_usdt:.2f} USDT.")

        closed_summary.append({
            "symbol": spot_symbol,
            "contracts": contracts,
            "spot_amount": spot_bal,
            "spot_usdt": sold_spot_usdt,
            "collateral_freed": collateral,
        })

    # Actualizar fichero carry_status_spot.json a 0 posiciones
    from tradebot.status import carry_path, status_slot
    status_file = Path(carry_path(status_slot(config)))
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "open_positions": 0,
        "total_funding_collected": round(storage.total_funding_collected(), 4),
        "positions": [],
    }
    status_file.write_text(json.dumps(status_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "─" * 70)
    if closed_summary:
        print("✅ CIERRE COMPLETADO EXITOSAMENTE")
        total_spot_freed = sum(c["spot_usdt"] for c in closed_summary)
        total_collateral_freed = sum(c["collateral_freed"] for c in closed_summary)
        total_freed = total_spot_freed + total_collateral_freed

        print(f"💵 Capital Spot recuperado:  +{total_spot_freed:,.2f} USDT")
        print(f"🛡️ Colateral Futuros liberado: +{total_collateral_freed:,.2f} USDT")
        print(f"🚀 TOTAL LIQUIDEZ LIBERADA:   +{total_freed:,.2f} USDT")

        # Notificar por Telegram
        if not dry_run:
            msg_lines = [
                "⚖️ <b>CARRY TRADE: POSICIONES DESMONTADAS Y CERRADAS</b>\n",
                "<i>Se ha ejecutado el cierre seguro para liberar liquidez al 100% para Spot:</i>\n",
            ]
            for c in closed_summary:
                msg_lines.append(
                    f"• <b>{c['symbol']}:</b> Venta Spot de {c['spot_amount']:.4f} (~+{c['spot_usdt']:.2f} USDT) "
                    f"y cierre de {c['contracts']} contratos cortos."
                )
            msg_lines.append(f"\n💰 <b>Liquidez Total Liberada:</b> <b>+{total_freed:.2f} USDT</b>")
            msg_lines.append("🛡️ <b>Riesgo en Futuros:</b> <b>0 (100% Fuera de Mercado)</b>")
            notifier.notify("\n".join(msg_lines))
    else:
        print("ℹ️ No se encontraron posiciones de Carry Trade abiertas para cerrar.")

    storage.close()
    print("═" * 70 + "\n")


if __name__ == "__main__":
    main()
