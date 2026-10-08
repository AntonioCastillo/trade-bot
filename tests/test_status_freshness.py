"""El status que sube el publicador debe estar al día: lo reescribe el hilo principal
en cada ciclo, de forma atómica, y el hilo publicador solo lee el fichero."""

import json
import sqlite3
import threading

from conftest import make_config, make_instrument

from tradebot import daemon, status
from tradebot.engine import Engine
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy import MeanReversionStrategy


def _engine(config, storage=None):
    strat = MeanReversionStrategy(rsi_period=14, rsi_oversold=30, bb_period=20, bb_std=2.0)
    return Engine(config, {config.instruments[0].symbol: strat}, RiskManager(config.risk),
                  PaperExecutionEngine(config), storage or Storage(":memory:"), enforce_daily_loss=False)


def _config():
    cfg = make_config(make_instrument(symbol="BNB/USDT", category="momentum1d"))
    cfg.carry.enabled = False
    return cfg


def test_refresh_status_rewrites_the_file_every_call(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = _config()
    engine = _engine(cfg)
    path = tmp_path / status.status_path(status.status_slot(cfg))

    assert daemon._refresh_status(engine, cfg) is True
    first = json.loads(path.read_text(encoding="utf-8"))

    engine.execution.set_balance(1234.5)                    # cambia el estado entre ciclos
    assert daemon._refresh_status(engine, cfg) is True
    second = json.loads(path.read_text(encoding="utf-8"))

    assert first["equity"] != second["equity"] == 1234.5
    assert list(path.parent.glob("*.tmp")) == []            # escritura atómica: sin restos


def test_refresh_status_never_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def boom(engine, config):
        raise OSError("disco lleno")

    monkeypatch.setattr(daemon, "write_status", boom)
    assert daemon._refresh_status(object(), object()) is False


def test_status_cannot_be_built_from_the_publisher_thread(tmp_path):
    """Por qué el publicador solo lee el fichero: la conexión SQLite es del hilo que la
    creó, así que construir el status desde otro hilo falla (antes, en silencio)."""
    cfg = _config()
    engine = _engine(cfg, storage=Storage(tmp_path / "bot.db"))
    errors = []

    def from_other_thread():
        try:
            status.build_status(engine, cfg)
        except Exception as exc:
            errors.append(exc)

    t = threading.Thread(target=from_other_thread)
    t.start()
    t.join()
    engine.storage.close()

    assert len(errors) == 1 and isinstance(errors[0], sqlite3.ProgrammingError)


def test_publisher_loop_only_reads_the_status_file(monkeypatch):
    """El hilo publicador sube lo que haya en disco y no toca el motor."""
    published, sleeps = [], []

    class Stop(Exception):
        pass

    def fake_sleep(seconds):
        sleeps.append(seconds)
        raise Stop                                           # corta el bucle tras la primera vuelta

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("TRADEBOT_GIST_ID", "abc123")
    monkeypatch.setattr(status, "load_unified", lambda *a, **k: {"instances": {"spot": {"equity": 1.0}}})
    monkeypatch.setattr("tradebot.publisher.publish_to_gist",
                        lambda st, token, gist_id: published.append((st, gist_id)) or {"id": gist_id, "created": False})
    monkeypatch.setattr(daemon.time, "sleep", fake_sleep)
    monkeypatch.setattr(threading, "excepthook", lambda args: None)   # el Stop del hilo no ensucia la salida

    touched = []

    class Untouchable:
        def __getattr__(self, name):
            touched.append(name)
            raise AssertionError(f"el publicador no debe usar el motor ({name})")

    thread = daemon._maybe_start_publisher(_config(), Untouchable())
    thread.join(timeout=5)

    assert touched == []
    assert published == [({"instances": {"spot": {"equity": 1.0}}}, "abc123")]
    assert sleeps == [daemon.PUBLISH_INTERVAL_SECONDS]
