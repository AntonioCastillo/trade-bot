"""Notificaciones de operaciones. Por defecto no hace nada (el engine ya escribe
en el log); si hay credenciales de Telegram, envía un mensaje por operación.

Los envíos nunca deben romper el bot: cualquier error de red se captura y se
registra, pero el trading continúa.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod

from typing import Any

from .telegram_views import (
    render_circuit_breaker_halt,
    render_execution_error,
    render_partial_tp,
    render_trade_closed,
    render_trade_opened,
)

logger = logging.getLogger(__name__)


class Notifier(ABC):
    @abstractmethod
    def notify(self, text: str) -> None: ...

    def notify_trade_opened(
        self, position: Any, head: str, signal_reason: str, equity: float, quote: str
    ) -> None:
        msg = render_trade_opened(position, head, signal_reason, equity, quote)
        self.notify(msg)

    def notify_trade_closed(
        self,
        symbol: str,
        entry_price: float,
        exit_price: float,
        reason: str,
        pnl_abs: float,
        pnl_pct: float,
        head: str,
        equity: float,
        quote: str,
    ) -> None:
        msg = render_trade_closed(
            symbol, entry_price, exit_price, reason, pnl_abs, pnl_pct, head, equity, quote
        )
        self.notify(msg)

    def notify_partial_tp(
        self,
        symbol: str,
        fill_price: float,
        head: str,
        pnl_abs: float,
        pnl_pct: float,
        stop_loss: float,
        equity: float,
        quote: str,
    ) -> None:
        msg = render_partial_tp(symbol, fill_price, head, pnl_abs, pnl_pct, stop_loss, equity, quote)
        self.notify(msg)

    def notify_circuit_breaker(self, current_dd: float, max_dd: float) -> None:
        msg = render_circuit_breaker_halt(current_dd, max_dd)
        self.notify(msg)

    def notify_execution_error(
        self, action: str, symbol: str, error: Any, details: str = ""
    ) -> None:
        msg = render_execution_error(action, symbol, error, details)
        self.notify(msg)


class NullNotifier(Notifier):
    """No envía nada. Es el valor por defecto (p.ej. en backtests)."""

    def notify(self, text: str) -> None:  # noqa: D401
        return None


class TelegramNotifier(Notifier):
    def __init__(self, token: str, chat_id: str, timeout: float = 10.0):
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout

    def notify(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = urllib.parse.urlencode(
            {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
        ).encode()
        try:
            with urllib.request.urlopen(url, data=data, timeout=self.timeout) as resp:
                if resp.status != 200:
                    logger.warning("Telegram respondió %s", resp.status)
        except Exception as e:  # nunca dejamos que un fallo de red pare el bot
            logger.warning("No se pudo enviar la notificación de Telegram: %s", e)


class PrefixNotifier(Notifier):
    """Envuelve otro notificador y antepone un prefijo a cada mensaje (p.ej. el
    modo), para que SIEMPRE quede claro si es simulación o real."""

    def __init__(self, inner: Notifier, prefix: str):
        self.inner = inner
        self.prefix = prefix

    def notify(self, text: str) -> None:
        self.inner.notify(f"{self.prefix} {text}")


def build_notifier(token: str | None, chat_id: str | None) -> Notifier:
    if token and chat_id:
        logger.info("Notificaciones de Telegram ACTIVADAS")
        return TelegramNotifier(token, chat_id)
    return NullNotifier()
