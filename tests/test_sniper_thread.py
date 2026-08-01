"""El sniper debe arrancar en el mismo proceso (un hilo) solo si está activado."""

import threading

from conftest import make_config, make_instrument

from tradebot import daemon
from tradebot.notifier import NullNotifier


def test_sniper_not_started_when_disabled():
    cfg = make_config(make_instrument())
    cfg.sniper.enabled = False
    assert daemon._maybe_start_sniper(cfg, NullNotifier()) is None


def test_sniper_started_in_thread_when_enabled(monkeypatch):
    started = threading.Event()

    class _FakeSniper:
        def __init__(self, *a, **k):
            pass

        def run_forever(self):
            started.set()

    monkeypatch.setattr(daemon, "Sniper", _FakeSniper)
    monkeypatch.setattr(daemon, "Exchange", lambda cfg: object())

    cfg = make_config(make_instrument())
    cfg.sniper.enabled = True
    thread = daemon._maybe_start_sniper(cfg, NullNotifier())

    assert thread is not None
    assert started.wait(timeout=2.0)   # el hilo llamó a run_forever
