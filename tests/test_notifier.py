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
from tradebot.strategy.mean_reversion import MeanReversionStrategy


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
