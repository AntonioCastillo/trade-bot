"""Reglas de pausa por cabeza: strikes (stops con pérdida) y pausa mientras otra
cabeza tenga posiciones abiertas. Solo bloquean ENTRADAS nuevas."""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from conftest import make_instrument

from tradebot.config import Config, RiskConfig, _build_instruments
from tradebot.engine import Engine
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.models import ClosedTrade, Side, Signal, SignalType
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.base import Strategy


class Switch(Strategy):
    """Estrategia de prueba: compra siempre que `buy` esté activo."""

    def __init__(self, buy: bool = True):
        self.buy = buy

    def generate_signal(self, symbol, candles):
        price = float(candles["close"].iloc[-1])
        return Signal(SignalType.BUY if self.buy else SignalType.HOLD, symbol, price)


class Recorder:
    def __init__(self):
        self.messages = []

    def notify(self, text):
        self.messages.append(text)

    def __getattr__(self, name):          # notify_trade_opened, notify_trade_closed…
        return lambda *a, **k: None


def _candles(price: float) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=1, freq="4h", tz="UTC")
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 1.0}, index=idx)


def _grid(**kw):
    ins = make_instrument(symbol="NEAR/USDT", category="grid", strategy_name="grid",
                          stop_loss_pct=0.05, take_profit_pct=0.50)
    for k, v in kw.items():
        setattr(ins, k, v)
    return ins


def _engine(instruments, storage=None, **kw):
    config = Config(instruments=instruments, risk=RiskConfig(starting_balance=10_000, max_open_positions=8))
    config.engine.fee_pct = 0.001
    config.engine.slippage_pct = 0.0
    strategies = {ins.symbol: Switch() for ins in instruments}
    risk = RiskManager(config.risk)
    risk.reset_day(config.risk.starting_balance)
    notifier = Recorder()
    engine = Engine(config, strategies=strategies, risk=risk, execution=PaperExecutionEngine(config),
                    storage=storage or Storage(":memory:"), enforce_daily_loss=False, notifier=notifier, **kw)
    return engine, notifier


def _lose(engine, symbol: str, start: float, times: int) -> float:
    """Abre en `start` y encadena `times` stops con pérdida (cada caída del 10%
    cierra la posición y la estrategia vuelve a entrar). Devuelve el último precio."""
    price = start
    engine.process(symbol, _candles(price))
    for _ in range(times):
        price *= 0.90
        engine.process(symbol, _candles(price))
    return price


def test_three_strikes_pause_the_head():
    engine, notifier = _engine([_grid(strike_limit=3)])
    _lose(engine, "NEAR/USDT", 100.0, 3)

    assert engine.storage.trade_count() == 3
    assert engine.positions == []                      # tras el 3er stop ya no reentra
    assert "grid" in engine.paused_heads()
    assert any("Cabeza en pausa" in m for m in notifier.messages)


def test_two_strikes_do_not_pause():
    engine, _ = _engine([_grid(strike_limit=3)])
    _lose(engine, "NEAR/USDT", 100.0, 2)

    assert len(engine.positions) == 1                  # sigue operando
    assert engine.paused_heads() == {}


def test_rule_disabled_by_default():
    engine, _ = _engine([_grid()])
    _lose(engine, "NEAR/USDT", 100.0, 5)

    assert len(engine.positions) == 1
    assert engine.paused_heads() == {}


def test_old_stops_outside_window_do_not_count():
    engine, _ = _engine([_grid(strike_limit=3, strike_window_days=7)])
    old = datetime.now(timezone.utc) - timedelta(days=10)
    for _ in range(2):
        engine.storage.record_closed_trade(ClosedTrade(
            symbol="NEAR/USDT", category="grid", strategy_name="grid", side=Side.BUY, amount=1.0,
            entry_price=100.0, exit_price=95.0, fee_total=0.1, pnl_abs=-5.1, pnl_pct=-5.1,
            exit_reason="stop-loss", opened_at=old - timedelta(hours=4), closed_at=old,
        ))
    _lose(engine, "NEAR/USDT", 100.0, 1)               # solo 1 stop reciente

    assert len(engine.positions) == 1
    assert engine.paused_heads() == {}


def test_winning_exits_are_not_strikes():
    engine, _ = _engine([_grid(strike_limit=1, take_profit_pct=0.05)])
    engine.process("NEAR/USDT", _candles(100.0))
    engine.process("NEAR/USDT", _candles(110.0))       # take-profit, en ganancia

    assert engine.storage.all_trades()[0]["exit_reason"] == "take-profit"
    assert engine.paused_heads() == {}


def test_pause_only_affects_its_own_head():
    other = make_instrument(symbol="ETH/USDT", category="volumen", stop_loss_pct=0.05, take_profit_pct=0.50)
    engine, _ = _engine([_grid(strike_limit=3), other])
    _lose(engine, "NEAR/USDT", 100.0, 3)
    engine.process("ETH/USDT", _candles(2000.0))

    assert [p.symbol for p in engine.positions] == ["ETH/USDT"]


def test_pause_survives_restart_and_expires():
    storage = Storage(":memory:")
    engine, _ = _engine([_grid(strike_limit=3, strike_pause_days=30)], storage=storage)
    price = _lose(engine, "NEAR/USDT", 100.0, 3)

    restarted, notifier = _engine([_grid(strike_limit=3, strike_pause_days=30)], storage=storage)
    restarted.process("NEAR/USDT", _candles(price))
    assert restarted.positions == []                   # la pausa sigue tras reiniciar

    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp()
    storage.set_state("pause_until:grid", past)        # la pausa ya venció
    restarted.process("NEAR/USDT", _candles(price))
    assert len(restarted.positions) == 1
    assert restarted.paused_heads() == {}
    assert any("Cabeza reanudada" in m for m in notifier.messages)


def test_strikes_that_caused_a_pause_do_not_retrigger():
    storage = Storage(":memory:")
    engine, _ = _engine([_grid(strike_limit=3)], storage=storage)
    price = _lose(engine, "NEAR/USDT", 100.0, 3)
    storage.set_state("pause_until:grid", (datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())

    engine.process("NEAR/USDT", _candles(price))       # reanuda y abre
    engine.process("NEAR/USDT", _candles(price * 0.90))  # 1 stop nuevo: no basta

    assert len(engine.positions) == 1
    assert engine.paused_heads() == {}


def test_open_positions_are_still_managed_during_pause():
    other = make_instrument(symbol="LINK/USDT", category="grid", strategy_name="grid",
                            stop_loss_pct=0.05, take_profit_pct=0.50)
    other.strike_limit = 3
    engine, _ = _engine([_grid(strike_limit=3), other])
    engine.process("LINK/USDT", _candles(10.0))        # posición abierta antes de la pausa
    _lose(engine, "NEAR/USDT", 100.0, 3)
    assert "grid" in engine.paused_heads()

    engine.process("LINK/USDT", _candles(8.0))         # su stop se ejecuta igualmente
    assert engine.positions == []


def test_paused_while_other_head_has_positions():
    bull = make_instrument(symbol="BTC/USDT", category="tendencia", stop_loss_pct=0.05, take_profit_pct=0.10)
    engine, _ = _engine([bull, _grid(paused_while_open=["tendencia"])])

    engine.process("BTC/USDT", _candles(50_000.0))
    engine.process("NEAR/USDT", _candles(100.0))
    assert [p.symbol for p in engine.positions] == ["BTC/USDT"]
    assert "grid" in engine.paused_heads()

    engine.strategies["BTC/USDT"].buy = False
    engine.process("BTC/USDT", _candles(56_000.0))     # la otra cabeza cierra en objetivo
    engine.process("NEAR/USDT", _candles(100.0))
    assert [p.symbol for p in engine.positions] == ["NEAR/USDT"]
    assert engine.paused_heads() == {}


def test_backtester_engine_ignores_pause_rules():
    engine, _ = _engine([_grid(strike_limit=3)], enforce_pause_rules=False)
    _lose(engine, "NEAR/USDT", 100.0, 4)

    assert len(engine.positions) == 1
    assert engine.paused_heads() == {}


def test_config_parses_pause_rules():
    universe = [
        {"name": "tendencia", "symbols": ["BTC/USDT"], "strategy": "breakout"},
        {"name": "grid", "symbols": ["NEAR/USDT"], "strategy": "grid",
         "strike_pause": {"strikes": 3, "window_days": 7, "pause_days": 30},
         "paused_while_open": ["tendencia"]},
    ]
    bull, grid = _build_instruments(universe, RiskConfig(), "4h")

    assert (grid.strike_limit, grid.strike_window_days, grid.strike_pause_days) == (3, 7.0, 30.0)
    assert grid.paused_while_open == ["tendencia"]
    assert bull.strike_limit == 0 and bull.paused_while_open == []


def test_disabled_head_is_skipped_and_can_be_referenced():
    universe = [
        {"name": "tendencia", "enabled": False, "symbols": ["BTC/USDT"], "strategy": "breakout"},
        {"name": "grid", "symbols": ["NEAR/USDT"], "strategy": "grid", "paused_while_open": ["tendencia"]},
    ]
    instruments = _build_instruments(universe, RiskConfig(), "4h")
    assert [i.symbol for i in instruments] == ["NEAR/USDT"]

    # Referenciar una cabeza desactivada no impide arrancar; una inexistente sí.
    Config(instruments=instruments, disabled_heads=["tendencia"]).validate()
    with pytest.raises(ValueError, match="paused_while_open"):
        Config(instruments=instruments).validate()


def test_config_rejects_unknown_head_in_paused_while_open():
    universe = [{"name": "grid", "symbols": ["NEAR/USDT"], "strategy": "grid",
                 "paused_while_open": ["no_existe"]}]
    config = Config(instruments=_build_instruments(universe, RiskConfig(), "4h"))

    with pytest.raises(ValueError, match="paused_while_open"):
        config.validate()
