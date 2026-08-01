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

logger = logging.getLogger(__name__)


class Notifier(ABC):
    @abstractmethod
    def notify(self, text: str) -> None: ...


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
