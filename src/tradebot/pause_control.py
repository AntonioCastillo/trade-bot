"""Pausa MANUAL por cabeza: un interruptor que el operador acciona a mano
(`scripts/manage.py pause|resume|pauses`), además de las reglas automáticas.

El estado vive en la tabla `state` de la base de datos del bot, que el motor
consulta en cada entrada: surte efecto sin reiniciar. Como las automáticas, solo
bloquea ENTRADAS nuevas; las posiciones abiertas se siguen gestionando.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .storage import Storage

FOREVER = 4102444800.0          # 2100-01-01 UTC: pausa sin fecha de fin


def manual_key(head: str) -> str:
    return f"manual_pause_until:{head}"


def strike_key(head: str) -> str:
    return f"pause_until:{head}"


def describe_until(until: float) -> str:
    """'hasta 2026-10-25 12:00 UTC' o 'sin fecha' para una pausa manual."""
    if until >= FOREVER:
        return "sin fecha (hasta que la reanudes)"
    return f"hasta {datetime.fromtimestamp(until, tz=timezone.utc):%Y-%m-%d %H:%M} UTC"


def pause_head(storage: Storage, head: str, days: float | None = None,
               now: datetime | None = None) -> float:
    """Pausa la cabeza `days` días (None = sin fecha). Devuelve el instante de fin."""
    if days is not None and days <= 0:
        raise ValueError("days debe ser mayor que 0")
    now = now or datetime.now(timezone.utc)
    until = FOREVER if days is None else (now + timedelta(days=days)).timestamp()
    storage.set_state(manual_key(head), until)
    return until


def resume_head(storage: Storage, head: str, now: datetime | None = None) -> list[str]:
    """Levanta la pausa manual y también la automática por strikes, si la hay.
    Devuelve qué pausas estaban activas ('manual', 'strikes')."""
    now_ts = (now or datetime.now(timezone.utc)).timestamp()
    lifted = []
    if (storage.get_state(manual_key(head)) or 0.0) > now_ts:
        lifted.append("manual")
    if (storage.get_state(strike_key(head)) or 0.0) > now_ts:
        lifted.append("strikes")
    storage.set_state(manual_key(head), 0.0)
    storage.set_state(strike_key(head), 0.0)
    return lifted


def active_pauses(storage: Storage, heads: list[str], now: datetime | None = None) -> dict[str, list[str]]:
    """Pausas vigentes por cabeza, en texto: {'grid_lateral': ['por strikes hasta …']}."""
    now_ts = (now or datetime.now(timezone.utc)).timestamp()
    out: dict[str, list[str]] = {}
    for head in heads:
        lines = []
        manual = storage.get_state(manual_key(head)) or 0.0
        if manual > now_ts:
            lines.append(f"manual {describe_until(manual)}")
        strikes = storage.get_state(strike_key(head)) or 0.0
        if strikes > now_ts:
            lines.append(f"por strikes hasta {datetime.fromtimestamp(strikes, tz=timezone.utc):%Y-%m-%d %H:%M} UTC")
        if lines:
            out[head] = lines
    return out
