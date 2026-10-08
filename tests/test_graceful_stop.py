"""Parada ordenada ante SIGTERM: al momento si el bot duerme, al acabar el ciclo si no."""

import signal

import pytest

from tradebot.daemon import _GracefulStop, _wait_cycle


class Recorder:
    def __init__(self):
        self.slept = []

    def sleep(self, seconds):
        self.slept.append(seconds)


def test_sleep_passes_through_when_no_stop_was_requested():
    rec = Recorder()
    stop = _GracefulStop(sleep=rec.sleep)
    stop.sleep(60)
    assert rec.slept == [60] and stop.requested is False


def test_signal_while_working_lets_the_cycle_finish_and_exits_at_the_next_sleep():
    rec = Recorder()
    stop = _GracefulStop(sleep=rec.sleep)

    stop._on_signal(signal.SIGTERM, None)          # llega a mitad de ciclo: no interrumpe
    assert stop.requested is True

    with pytest.raises(KeyboardInterrupt):         # el ciclo terminó; al ir a esperar, sale
        stop.sleep(60)
    assert rec.slept == []                         # sin llegar a dormir


def test_signal_while_sleeping_exits_immediately():
    stop = _GracefulStop()

    def interrupted_sleep(seconds):
        stop._on_signal(signal.SIGTERM, None)      # la señal llega durante la espera

    stop._sleep = interrupted_sleep
    with pytest.raises(KeyboardInterrupt):
        stop.sleep(60)
    assert stop._sleeping is False


def test_wait_cycle_stops_between_polls():
    class Engine:
        positions = []

    rec = Recorder()
    stop = _GracefulStop(sleep=rec.sleep)
    _wait_cycle(Engine(), 60, 10, {}, sleep=stop.sleep, clock=lambda: 0.0)
    assert rec.slept == [60]

    stop._on_signal(signal.SIGTERM, None)
    with pytest.raises(KeyboardInterrupt):
        _wait_cycle(Engine(), 60, 10, {}, sleep=stop.sleep, clock=lambda: 0.0)


def test_install_registers_the_handler_and_restores_cleanly():
    previous = signal.getsignal(signal.SIGTERM)
    stop = _GracefulStop()
    try:
        assert stop.install() is True
        assert signal.getsignal(signal.SIGTERM) == stop._on_signal
    finally:
        signal.signal(signal.SIGTERM, previous)
