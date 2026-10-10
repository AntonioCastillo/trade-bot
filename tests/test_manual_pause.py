"""Pausa manual por cabeza (manage.py pause/resume): bloquea solo entradas nuevas,
vale para cualquier cabeza, surte efecto sin reiniciar y convive con la de strikes."""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from conftest import make_instrument

from tradebot import pause_control as pc
from tradebot.config import Config, RiskConfig
from tradebot.engine import Engine
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.models import Signal, SignalType
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.base import Strategy


class Switch(Strategy):
    def __init__(self):
        self.buy = True

    def generate_signal(self, symbol, candles):
        price = float(candles["close"].iloc[-1])
        return Signal(SignalType.BUY if self.buy else SignalType.HOLD, symbol, price)


class Recorder:
    def __init__(self):
        self.messages = []

    def notify(self, text):
        self.messages.append(text)

    def __getattr__(self, name):
        return lambda *a, **k: None


def _candles(price: float) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=1, freq="4h", tz="UTC")
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 1.0}, index=idx)


def _engine(storage=None, strike_limit=0):
    grid = make_instrument(symbol="NEAR/USDT", category="grid", stop_loss_pct=0.05, take_profit_pct=0.50)
    grid.strike_limit, grid.strike_pause_days = strike_limit, 30
    other = make_instrument(symbol="ETH/USDT", category="volumen", stop_loss_pct=0.05, take_profit_pct=0.50)
    config = Config(instruments=[grid, other], risk=RiskConfig(starting_balance=10_000, max_open_positions=8))
    config.engine.fee_pct, config.engine.slippage_pct = 0.001, 0.0
    risk = RiskManager(config.risk)
    risk.reset_day(config.risk.starting_balance)
    notifier = Recorder()
    engine = Engine(config, strategies={"NEAR/USDT": Switch(), "ETH/USDT": Switch()}, risk=risk,
                    execution=PaperExecutionEngine(config), storage=storage or Storage(":memory:"),
                    enforce_daily_loss=False, notifier=notifier)
    return engine, notifier


def test_manual_pause_blocks_only_that_head_even_without_strike_rule():
    engine, _ = _engine()
    pc.pause_head(engine.storage, "grid")

    engine.process("NEAR/USDT", _candles(100.0))
    engine.process("ETH/USDT", _candles(100.0))

    assert [p.symbol for p in engine.positions] == ["ETH/USDT"]
    assert engine.paused_heads() == {"grid": "manual sin fecha (hasta que la reanudes)"}


def test_open_positions_are_still_managed_during_manual_pause():
    engine, _ = _engine()
    engine.process("NEAR/USDT", _candles(100.0))
    pc.pause_head(engine.storage, "grid")

    engine.process("NEAR/USDT", _candles(90.0))                 # salta el stop del 5%

    assert engine.positions == []                               # cierra…
    assert engine.storage.all_trades()[0]["exit_reason"] == "stop-loss"
    engine.process("NEAR/USDT", _candles(90.0))
    assert engine.positions == []                               # …y no vuelve a entrar


def test_pause_with_days_expires_and_announces_it():
    engine, notifier = _engine()
    start = datetime.now(timezone.utc) - timedelta(days=3)
    until = pc.pause_head(engine.storage, "grid", days=2, now=start)   # venció ayer
    assert until == pytest.approx((start + timedelta(days=2)).timestamp())

    engine.process("NEAR/USDT", _candles(100.0))

    assert len(engine.positions) == 1
    assert engine.paused_heads() == {}
    assert engine.storage.get_state(pc.manual_key("grid")) == 0.0
    assert any("Cabeza reanudada" in m and "manual" in m for m in notifier.messages)


def test_pause_with_days_shows_its_end_date():
    engine, _ = _engine()
    now = datetime.now(timezone.utc)
    pc.pause_head(engine.storage, "grid", days=15, now=now)

    engine.process("NEAR/USDT", _candles(100.0))

    assert engine.positions == []
    assert engine.paused_heads()["grid"] == f"manual hasta {now + timedelta(days=15):%Y-%m-%d %H:%M} UTC"


def test_resume_lifts_manual_and_strike_pauses():
    engine, _ = _engine(strike_limit=3)
    future = (datetime.now(timezone.utc) + timedelta(days=20)).timestamp()
    engine.storage.set_state(pc.strike_key("grid"), future)     # en pausa por strikes
    pc.pause_head(engine.storage, "grid")                       # y además manual
    engine.process("NEAR/USDT", _candles(100.0))
    assert engine.positions == []

    assert pc.resume_head(engine.storage, "grid") == ["manual", "strikes"]
    engine.process("NEAR/USDT", _candles(100.0))

    assert len(engine.positions) == 1
    assert engine.paused_heads() == {}
    assert pc.resume_head(engine.storage, "grid") == []         # ya no había nada que levantar


def test_pause_written_by_another_process_takes_effect_without_restart(tmp_path):
    db = tmp_path / "bot.db"
    engine, _ = _engine(storage=Storage(db))
    engine.process("ETH/USDT", _candles(100.0))                 # el bot ya está funcionando

    cli = Storage(db)                                           # manage.py abre su propia conexión
    pc.pause_head(cli, "grid", days=7)
    cli.close()
    engine.process("NEAR/USDT", _candles(100.0))
    assert [p.symbol for p in engine.positions] == ["ETH/USDT"]

    cli = Storage(db)
    pc.resume_head(cli, "grid")
    cli.close()
    engine.process("NEAR/USDT", _candles(100.0))
    assert sorted(p.symbol for p in engine.positions) == ["ETH/USDT", "NEAR/USDT"]
    engine.storage.close()


def test_active_pauses_lists_both_kinds():
    storage = Storage(":memory:")
    now = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
    storage.set_state(pc.strike_key("grid"), (now + timedelta(days=27)).timestamp())
    pc.pause_head(storage, "volumen", days=2, now=now)

    assert pc.active_pauses(storage, ["grid", "volumen", "capitulacion"], now=now) == {
        "grid": ["por strikes hasta 2026-11-07 12:00 UTC"],
        "volumen": ["manual hasta 2026-10-13 12:00 UTC"],
    }
    assert pc.active_pauses(storage, ["grid", "volumen"], now=now + timedelta(days=40)) == {}


def test_pause_rejects_non_positive_days():
    with pytest.raises(ValueError):
        pc.pause_head(Storage(":memory:"), "grid", days=0)
