from conftest import make_config, make_instrument

from tradebot.engine import Engine
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.notifier import (
    NullNotifier,
    PrefixNotifier,
    TelegramNotifier,
    build_notifier,
)
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy import MeanReversionStrategy


class _Capture(NullNotifier):
    def __init__(self):
        self.messages = []

    def notify(self, text):
        self.messages.append(text)


def test_build_notifier_null_without_credentials():
    assert isinstance(build_notifier("", ""), NullNotifier)
    assert isinstance(build_notifier("tok", ""), NullNotifier)


def test_build_notifier_telegram_with_credentials():
    n = build_notifier("token", "chat")
    assert isinstance(n, TelegramNotifier)


def test_telegram_notify_swallows_network_errors(monkeypatch):
    def boom(*a, **k):
        raise OSError("sin red")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    # No debe lanzar: un fallo de red nunca puede parar el bot.
    TelegramNotifier("t", "c").notify("hola")


def test_prefix_notifier_prepends_mode():
    cap = _Capture()
    PrefixNotifier(cap, "🧪 [SIMULACIÓN]").notify("ABRE BTC/USDT")
    assert cap.messages == ["🧪 [SIMULACIÓN] ABRE BTC/USDT"]


def test_engine_notifies_on_open(price_series):
    config = make_config(make_instrument(symbol="BTC/USDT"))
    cap = _Capture()
    strat = MeanReversionStrategy(rsi_period=14, rsi_oversold=35, bb_period=20, bb_std=2.0)
    risk = RiskManager(config.risk)
    engine = Engine(config, {"BTC/USDT": strat}, risk, PaperExecutionEngine(config),
                    Storage(":memory:"), enforce_daily_loss=False, notifier=cap)

    prices = [100.0] * 25 + [95, 90, 85, 80, 70]
    engine.process("BTC/USDT", price_series(prices))

    assert any("ABRE" in m for m in cap.messages)


def test_typed_domain_notifications():
    cap = _Capture()
    from tradebot.models import Position, Side

    pos = Position(
        symbol="ETH/USDT",
        side=Side.BUY,
        amount=1.0,
        entry_price=2500.0,
        stop_loss=2400.0,
        take_profit=2700.0,
    )

    cap.notify_trade_opened(pos, "majors/trend", "breakout signal", 1000.0, "USDT")
    assert len(cap.messages) == 1
    assert "<b>ABRE</b> BUY ETH/USDT" in cap.messages[0]
    assert "majors/trend" in cap.messages[0]

    cap.notify_partial_tp("ETH/USDT", 2625.0, "majors/trend", 125.0, 5.0, 2500.0, 1125.0, "USDT")
    assert len(cap.messages) == 2
    assert "TOMA PARCIAL" in cap.messages[1]
    assert "+125.00 USDT" in cap.messages[1]

    cap.notify_trade_closed("ETH/USDT", 2500.0, 2700.0, "take-profit", 200.0, 8.0, "majors/trend", 1200.0, "USDT")
    assert len(cap.messages) == 3
    assert "CIERRA" in cap.messages[2]
    assert "+200.00 USDT" in cap.messages[2]

    cap.notify_circuit_breaker(0.16, 0.15)
    assert len(cap.messages) == 4
    assert "DISYUNTOR CRÍTICO" in cap.messages[3]

    cap.notify_execution_error("cerrar posición", "ETH/USDT", "timeout", "reintentando...")
    assert len(cap.messages) == 5
    assert "ERROR EN CERRAR POSICIÓN" in cap.messages[4]

