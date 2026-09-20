"""Planificador de eventos y tareas periódicas para el daemon de trading.

Maneja de forma limpia los cortes horarios (00:00 UTC, slots de 4H, pings y reportes).
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone


class EventScheduler:
    """Controla la temporización de eventos periódicos en el bucle principal."""

    def __init__(
        self,
        report_interval_seconds: int = 900,
        alive_interval_seconds: int = 21600,
        error_notify_interval_seconds: int = 1800,
    ):
        self.report_interval = report_interval_seconds
        self.alive_interval = alive_interval_seconds
        self.error_notify_interval = error_notify_interval_seconds

        now = datetime.now(timezone.utc)
        self.current_day: date = now.date()
        self.last_4h_slot: tuple[date, int] = (now.date(), now.hour // 4)

        t_now = time.time()
        self.last_report_ts: float = t_now
        self.last_alive_ts: float = t_now
        self.last_error_notify_ts: float = 0.0

    def is_new_utc_day(self, dt: datetime) -> bool:
        """Devuelve True si ha cambiado el día UTC (00:00 UTC medianoche)."""
        if dt.date() != self.current_day:
            self.current_day = dt.date()
            return True
        return False

    def check_4h_slot(self, dt: datetime) -> bool:
        """Devuelve True en cada cambio de bloque de 4H (00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC)."""
        slot = (dt.date(), dt.hour // 4)
        if slot != self.last_4h_slot:
            self.last_4h_slot = slot
            return True
        return False

    def is_report_due(self, t_now: float | None = None) -> bool:
        """Devuelve True si toca generar/publicar el informe periódico."""
        t = t_now if t_now is not None else time.time()
        if (t - self.last_report_ts) >= self.report_interval:
            self.last_report_ts = t
            return True
        return False

    def is_alive_due(self, t_now: float | None = None) -> bool:
        """Devuelve True si toca enviar la señal de vida periódica a Telegram."""
        t = t_now if t_now is not None else time.time()
        if (t - self.last_alive_ts) >= self.alive_interval:
            self.last_alive_ts = t
            return True
        return False

    def can_notify_error(self, t_now: float | None = None) -> bool:
        """Rate limit para no saturar con notificaciones de error consecutivas."""
        t = t_now if t_now is not None else time.time()
        if (t - self.last_error_notify_ts) >= self.error_notify_interval:
            self.last_error_notify_ts = t
            return True
        return False
