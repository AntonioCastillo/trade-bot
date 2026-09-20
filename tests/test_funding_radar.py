"""Tests para el Radar de Tasas de Financiación (>25% anual)."""

import pytest
from conftest import make_config, make_instrument

from tradebot.funding_radar import evaluate_funding_radar
from tradebot.notifier import NullNotifier


class FakeNotifier:
    def __init__(self):
        self.messages: list[str] = []

    def notify(self, message: str) -> None:
        self.messages.append(message)


class FakeExchange:
    def __init__(self, rates: dict[str, float]):
        self.rates = rates

    def fetch_funding_history(self, symbol: str, limit: int = 1) -> list[dict]:
        clean = symbol.replace(":USDT", "")
        if clean in self.rates:
            return [{"fundingRate": self.rates[clean], "timestamp": 1000}]
        return []


def test_radar_no_alert_when_rates_low():
    cfg = make_config(make_instrument())
    cfg.carry.funding_radar_enabled = True
    cfg.carry.radar_min_annualized_pct = 25.0
    cfg.carry.radar_symbols = ["ETH/USDT", "SOL/USDT"]

    # 0.0001 (0.01% por 8h) = ~10.95% anual < 25%
    exchange = FakeExchange({"ETH/USDT": 0.0001, "SOL/USDT": 0.0001})
    notifier = FakeNotifier()
    cooldowns: dict[str, float] = {}

    alerts = evaluate_funding_radar(cfg, exchange, notifier, cooldowns)
    assert len(alerts) == 0
    assert len(notifier.messages) == 0


def test_radar_alerts_when_rate_exceeds_threshold():
    cfg = make_config(make_instrument())
    cfg.carry.funding_radar_enabled = True
    cfg.carry.radar_min_annualized_pct = 25.0
    cfg.carry.radar_symbols = ["SOL/USDT"]

    # 0.0003 (0.03% por 8h) = 32.85% anual >= 25%
    exchange = FakeExchange({"SOL/USDT": 0.0003})
    notifier = FakeNotifier()
    cooldowns: dict[str, float] = {}

    alerts = evaluate_funding_radar(cfg, exchange, notifier, cooldowns)
    assert len(alerts) == 1
    assert alerts[0]["symbol"] == "SOL/USDT"
    assert alerts[0]["annualized_pct"] == pytest.approx(32.85)
    assert len(notifier.messages) == 1
    assert "RADAR DE FUNDING" in notifier.messages[0]
    assert "SOL/USDT" in notifier.messages[0]


def test_radar_cooldown_prevents_duplicate_alerts():
    cfg = make_config(make_instrument())
    cfg.carry.funding_radar_enabled = True
    cfg.carry.radar_min_annualized_pct = 25.0
    cfg.carry.radar_symbols = ["SOL/USDT"]

    exchange = FakeExchange({"SOL/USDT": 0.0004})
    notifier = FakeNotifier()
    cooldowns: dict[str, float] = {}

    # Primer escaneo -> alerta
    alerts1 = evaluate_funding_radar(cfg, exchange, notifier, cooldowns)
    assert len(alerts1) == 1
    assert len(notifier.messages) == 1

    # Segundo escaneo inmediato -> cooldown activo, no re-alerta
    alerts2 = evaluate_funding_radar(cfg, exchange, notifier, cooldowns)
    assert len(alerts2) == 0
    assert len(notifier.messages) == 1  # No se añadió ningún mensaje nuevo
