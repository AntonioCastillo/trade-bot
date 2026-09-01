"""Limpia registros de estrategias antiguas/deprecadas (p.ej. scalping5m) de la BD SQLite.

Uso en VPS o local:
    python scripts/cleanup_legacy.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def clean_db(db_path: Path) -> None:
    if not db_path.exists():
        return

    print(f"[+] Limpiando: {db_path}...")
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Eliminar operaciones de scalping antiguo
    cur.execute(
        "DELETE FROM closed_trades WHERE category = 'scalping5m' OR strategy = 'scalping'"
    )
    deleted_closed = cur.rowcount

    cur.execute(
        "DELETE FROM fills WHERE reason LIKE '%scalping%' OR reason LIKE '%scalp%'"
    )
    deleted_fills = cur.rowcount

    conn.commit()

    # Mostrar nuevo resumen
    cur.execute("SELECT COUNT(*), SUM(pnl_abs), SUM(CASE WHEN pnl_abs > 0 THEN 1 ELSE 0 END) FROM closed_trades")
    row = cur.fetchone()
    trades, pnl, wins = row[0], row[1] or 0.0, row[2] or 0
    wr = (wins / trades * 100) if trades > 0 else 0.0

    conn.close()

    print(f"    ✓ Eliminados {deleted_closed} trades cerrados de scalping ({deleted_fills} fills).")
    print(f"    ✓ Nuevo estado real: {trades} trades | {wins} aciertos | Win Rate: {wr:.1f}% | P&L: {pnl:+.2f} USDT\n")


def main() -> None:
    data_dir = Path("data")
    for db_name in ["tradebot_live.db", "tradebot_paper.db", "tradebot.db"]:
        clean_db(data_dir / db_name)
    print("✨ Limpieza completada con éxito.")


if __name__ == "__main__":
    main()
