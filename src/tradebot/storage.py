"""Persistencia en SQLite.

Dos niveles:
  - `fills`: cada ejecución individual (auditoría).
  - `closed_trades`: cada round-trip completo con su P&L realizado. Es la tabla
    que se consulta para evaluar viabilidad (por operación, por símbolo, etc.).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import ClosedTrade, Fill, Position, Side

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

CREATE TABLE IF NOT EXISTS open_positions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol            TEXT NOT NULL,
    side              TEXT NOT NULL,
    amount            REAL NOT NULL,
    entry_price       REAL NOT NULL,
    stop_loss         REAL NOT NULL,
    take_profit       REAL NOT NULL,
    category          TEXT NOT NULL,
    strategy          TEXT NOT NULL,
    entry_fee         REAL NOT NULL,
    reason            TEXT,
    trailing_stop_pct REAL NOT NULL,
    peak_price        REAL NOT NULL,
    bars_held         INTEGER NOT NULL,
    partial_tp_pct    REAL DEFAULT 0.0,
    partial_tp_ratio  REAL DEFAULT 0.5,
    partial_tp_done   INTEGER DEFAULT 0,
    opened_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value REAL NOT NULL
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
        for col_name, col_type in [
            ("partial_tp_pct", "REAL DEFAULT 0.0"),
            ("partial_tp_ratio", "REAL DEFAULT 0.5"),
            ("partial_tp_done", "INTEGER DEFAULT 0"),
        ]:
            try:
                self._conn.execute(f"ALTER TABLE open_positions ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass
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

    # --- Posiciones abiertas (persistencia para reinicios) -------------------------

    def save_open_position(self, pos: Position) -> int:
        """Inserta la posición abierta y le fija `db_id` (para luego actualizar/borrar)."""
        cur = self._conn.execute(
            "INSERT INTO open_positions (symbol, side, amount, entry_price, stop_loss,"
            " take_profit, category, strategy, entry_fee, reason, trailing_stop_pct,"
            " peak_price, bars_held, partial_tp_pct, partial_tp_ratio, partial_tp_done, opened_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                pos.symbol, pos.side.value, pos.amount, pos.entry_price, pos.stop_loss,
                pos.take_profit, pos.category, pos.strategy_name, pos.entry_fee, pos.reason,
                pos.trailing_stop_pct, pos.peak_price, pos.bars_held,
                pos.partial_tp_pct, pos.partial_tp_ratio, int(pos.partial_tp_done),
                pos.opened_at.isoformat(),
            ),
        )
        self._conn.commit()
        pos.db_id = int(cur.lastrowid)
        return pos.db_id

    def update_open_position(self, pos: Position) -> None:
        """Persiste los campos que mutan mientras vive (trailing, velas aguantadas, TP parcial y
        el importe, que puede ajustarse en la reconciliación o tras salida parcial)."""
        if not pos.db_id:
            return
        self._conn.execute(
            "UPDATE open_positions SET stop_loss=?, peak_price=?, bars_held=?, amount=?,"
            " partial_tp_done=? WHERE id=?",
            (pos.stop_loss, pos.peak_price, pos.bars_held, pos.amount, int(pos.partial_tp_done), pos.db_id),
        )
        self._conn.commit()

    def delete_open_position(self, pos: Position) -> None:
        if not pos.db_id:
            return
        self._conn.execute("DELETE FROM open_positions WHERE id=?", (pos.db_id,))
        self._conn.commit()

    def load_open_positions(self) -> list[Position]:
        """Reconstruye las posiciones abiertas persistidas (para readoptarlas al arrancar)."""
        from datetime import datetime

        rows = self._conn.execute("SELECT * FROM open_positions ORDER BY id").fetchall()
        out: list[Position] = []
        for r in rows:
            keys = r.keys()
            pos = Position(
                symbol=r["symbol"], side=Side(r["side"]), amount=r["amount"],
                entry_price=r["entry_price"], stop_loss=r["stop_loss"],
                take_profit=r["take_profit"], category=r["category"],
                strategy_name=r["strategy"], entry_fee=r["entry_fee"], reason=r["reason"] or "",
                trailing_stop_pct=r["trailing_stop_pct"], peak_price=r["peak_price"],
                bars_held=int(r["bars_held"]),
                partial_tp_pct=float(r["partial_tp_pct"]) if "partial_tp_pct" in keys and r["partial_tp_pct"] is not None else 0.0,
                partial_tp_ratio=float(r["partial_tp_ratio"]) if "partial_tp_ratio" in keys and r["partial_tp_ratio"] is not None else 0.5,
                partial_tp_done=bool(r["partial_tp_done"]) if "partial_tp_done" in keys and r["partial_tp_done"] is not None else False,
                opened_at=datetime.fromisoformat(r["opened_at"]),
                db_id=int(r["id"]),
            )
            out.append(pos)
        return out

    # --- Estado clave/valor (p.ej. efectivo simulado en paper) ---------------------

    def set_state(self, key: str, value: float) -> None:
        self._conn.execute(
            "INSERT INTO state (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, float(value)),
        )
        self._conn.commit()

    def get_state(self, key: str, default: float | None = None) -> float | None:
        row = self._conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return float(row["value"]) if row else default

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
