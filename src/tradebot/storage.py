"""Persistencia en SQLite.

Dos niveles:
  - `fills`: cada ejecución individual (auditoría).
  - `closed_trades`: cada round-trip completo con su P&L realizado. Es la tabla
    que se consulta para evaluar viabilidad (por operación, por símbolo, etc.).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import ClosedTrade, Fill

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fills (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    side          TEXT NOT NULL,
    amount        REAL NOT NULL,
    price         REAL NOT NULL,
    fee           REAL NOT NULL,
    reason        TEXT
);

CREATE TABLE IF NOT EXISTS closed_trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT NOT NULL,
    category      TEXT NOT NULL,
    strategy      TEXT NOT NULL,
    side          TEXT NOT NULL,
    amount        REAL NOT NULL,
    entry_price   REAL NOT NULL,
    exit_price    REAL NOT NULL,
    fee_total     REAL NOT NULL,
    pnl_abs       REAL NOT NULL,
    pnl_pct       REAL NOT NULL,
    exit_reason   TEXT NOT NULL,
    opened_at     TEXT NOT NULL,
    closed_at     TEXT NOT NULL,
    duration_s    REAL NOT NULL
);
"""


class Storage:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        if self.db_path not in (":memory:",):
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- Escritura -----------------------------------------------------------------

    def record_fill(self, fill: Fill) -> None:
        self._conn.execute(
            "INSERT INTO fills (timestamp, symbol, side, amount, price, fee, reason)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                fill.timestamp.isoformat(), fill.order.symbol, fill.order.side.value,
                fill.filled_amount, fill.filled_price, fill.fee, fill.order.reason,
            ),
        )
        self._conn.commit()

    def record_closed_trade(self, trade: ClosedTrade) -> None:
        self._conn.execute(
            "INSERT INTO closed_trades (symbol, category, strategy, side, amount,"
            " entry_price, exit_price, fee_total, pnl_abs, pnl_pct, exit_reason,"
            " opened_at, closed_at, duration_s)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                trade.symbol, trade.category, trade.strategy_name, trade.side.value,
                trade.amount, trade.entry_price, trade.exit_price, trade.fee_total,
                trade.pnl_abs, trade.pnl_pct, trade.exit_reason,
                trade.opened_at.isoformat(), trade.closed_at.isoformat(),
                trade.duration_seconds,
            ),
        )
        self._conn.commit()

    # --- Consulta ------------------------------------------------------------------

    def trade_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM closed_trades").fetchone()[0])

    def fill_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0])

    def all_trades(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM closed_trades ORDER BY closed_at"
        ).fetchall()

    def summary(self) -> dict:
        """Estadísticas globales sobre las operaciones cerradas."""
        row = self._conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(pnl_abs), 0) pnl,"
            " COALESCE(AVG(pnl_pct), 0) avg_pct,"
            " SUM(CASE WHEN pnl_abs > 0 THEN 1 ELSE 0 END) wins"
            " FROM closed_trades"
        ).fetchone()
        n = int(row["n"])
        return {
            "trades": n,
            "pnl_abs": float(row["pnl"]),
            "avg_pnl_pct": float(row["avg_pct"]),
            "wins": int(row["wins"] or 0),
            "win_rate": (int(row["wins"] or 0) / n) if n else 0.0,
        }

    def summary_by(self, column: str) -> list[sqlite3.Row]:
        """Agrupa el P&L por 'symbol', 'category' o 'strategy'."""
        if column not in ("symbol", "category", "strategy"):
            raise ValueError("column debe ser symbol, category o strategy")
        return self._conn.execute(
            f"SELECT {column} AS grp, COUNT(*) trades,"
            " SUM(pnl_abs) pnl_abs, AVG(pnl_pct) avg_pnl_pct,"
            " SUM(CASE WHEN pnl_abs > 0 THEN 1 ELSE 0 END) wins"
            f" FROM closed_trades GROUP BY {column} ORDER BY pnl_abs DESC"
        ).fetchall()

    def close(self) -> None:
        self._conn.close()
