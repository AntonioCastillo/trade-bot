"""Status del bot como dict/JSON, para publicarlo (p.ej. a un gist) y poder
leerlo desde fuera. Incluye modo, equity, P&L, cabezas activas y desglose por
cabeza. El resumen del sniper se fusiona aparte (lo escribe su propio hilo)."""

from __future__ import annotations

import json
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_STATUS_PATH = "data/status.json"
DEFAULT_SNIPER_PATH = "data/sniper_status.json"
DEFAULT_XSMOM_PATH = "data/xsmom_status.json"


def active_heads(config) -> list[dict]:
    """Cabezas activas agrupadas por categoría, con su estrategia/tf/símbolos."""
    groups: "OrderedDict[str, dict]" = OrderedDict()
    for ins in config.instruments:
        g = groups.setdefault(ins.category, {
            "name": ins.category, "strategy": ins.strategy_name,
            "timeframe": ins.timeframe, "symbols": [],
        })
        g["symbols"].append(ins.symbol)
    return list(groups.values())


def build_status(engine, config) -> dict[str, Any]:
    """Snapshot estructurado del estado del bot (solo lo persistido/calculable)."""
    s = engine.storage.summary()
    try:
        equity = round(engine.equity(), 2)
    except Exception:
        equity = None

    by_head: list[dict] = []
    try:
        for r in engine.storage.summary_by("category"):
            by_head.append({
                "head": r["grp"], "trades": int(r["trades"]),
                "pnl_abs": round(float(r["pnl_abs"] or 0), 2),
                "wins": int(r["wins"] or 0),
            })
    except Exception:
        pass

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": config.mode,
        "quote": config.risk.quote_currency,
        "equity": equity,
        "starting_balance": config.risk.starting_balance,
        "closed_trades": s["trades"],
        "pnl_abs": round(s["pnl_abs"], 2),
        "win_rate": round(s["win_rate"], 3),
        "avg_pnl_pct": round(s["avg_pnl_pct"], 3),
        "halted": engine.risk.halted,
        "heads": active_heads(config),
        "by_head": by_head,
        "sniper_enabled": config.sniper.enabled,
        "carry_enabled": config.carry.enabled,
    }


def write_status(engine, config, path: str = DEFAULT_STATUS_PATH) -> None:
    """Vuelca el status a disco (JSON). Lo llama el daemon en cada informe."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(build_status(engine, config), indent=2, ensure_ascii=False),
                 encoding="utf-8")


def _merge_file(status: dict, key: str, path: str) -> dict:
    """Fusiona en `status[key]` el JSON de un subsistema (sniper/xsmom), si existe."""
    p = Path(path)
    if p.exists():
        try:
            status[key] = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return status


def merge_sniper(status: dict, sniper_path: str = DEFAULT_SNIPER_PATH) -> dict:
    """Añade al status el resumen del sniper (que su hilo deja en JSON), si existe."""
    return _merge_file(status, "sniper", sniper_path)


def merge_xsmom(status: dict, xsmom_path: str = DEFAULT_XSMOM_PATH) -> dict:
    """Añade al status el resumen del momentum transversal, si existe."""
    return _merge_file(status, "xsmom", xsmom_path)


def load_merged(status_path: str = DEFAULT_STATUS_PATH,
                sniper_path: str = DEFAULT_SNIPER_PATH,
                xsmom_path: str = DEFAULT_XSMOM_PATH) -> dict:
    """Carga el status.json de disco y le fusiona los subsistemas. Para publicar."""
    data = json.loads(Path(status_path).read_text(encoding="utf-8"))
    merge_sniper(data, sniper_path)
    return merge_xsmom(data, xsmom_path)
