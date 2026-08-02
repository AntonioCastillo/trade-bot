"""El carry debe arrancar en un hilo del daemon solo si está activado."""

import threading

from conftest import make_config, make_instrument

from tradebot import daemon
from tradebot.notifier import NullNotifier


def test_carry_not_started_when_disabled():
    cfg = make_config(make_instrument())
    cfg.carry.enabled = False
    assert daemon._maybe_start_carry(cfg, NullNotifier()) is None


def test_carry_started_in_thread_when_enabled(monkeypatch):
    started = threading.Event()

    class _FakeRunner:
        def __init__(self, *a, **k):
            pass

        def run_forever(self):
            started.set()

    monkeypatch.setattr(daemon, "CarryRunner", _FakeRunner)
    monkeypatch.setattr(daemon, "Exchange", lambda cfg: object())

    cfg = make_config(make_instrument())
    cfg.carry.enabled = True
    thread = daemon._maybe_start_carry(cfg, NullNotifier())

    assert thread is not None
    assert started.wait(timeout=2.0)
