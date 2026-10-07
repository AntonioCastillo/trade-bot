"""Medición del deslizamiento real de los stops y sondeo rápido de las posiciones
abiertas entre ciclos."""

import sqlite3
from datetime import datetime, timezone

import pandas as pd
import pytest
from conftest import make_instrument

from tradebot.config import Config, RiskConfig
from tradebot.daemon import _poll_open_exits, _wait_cycle
from tradebot.engine import Engine
from tradebot.exchange import Exchange
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.models import ClosedTrade, Side, Signal, SignalType
from tradebot.reporting import render_report
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.base import Strategy


class Switch(Strategy):
    def __init__(self, buy: bool = True):
        self.buy = buy

    def generate_signal(self, symbol, candles):
        price = float(candles["close"].iloc[-1])
        return Signal(SignalType.BUY if self.buy else SignalType.HOLD, symbol, price)


class FakeExchange:
    """Devuelve los precios configurados y cuenta las consultas."""

    def __init__(self, prices=None, fail=False):
        self.prices, self.fail, self.calls = prices or {}, fail, []

    def fetch_last_prices(self, symbols):
        self.calls.append(list(symbols))
        if self.fail:
            raise ConnectionError("sin red")
        return {s: self.prices[s] for s in symbols if s in self.prices}


class FakeClock:
    """Reloj que avanza solo cuando se 'duerme'."""

    def __init__(self):
        self.now, self.sleeps = 0.0, []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 6))
        self.now += seconds


def _candles(price: float) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=1, freq="4h", tz="UTC")
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 1.0}, index=idx)


def _engine(exchange=None, **ins_kw):
    ins = make_instrument(symbol="ADA/USDT", category="volumen", stop_loss_pct=0.05, take_profit_pct=0.20, **ins_kw)
    config = Config(instruments=[ins], risk=RiskConfig(starting_balance=10_000))
    config.engine.fee_pct = 0.001
    config.engine.slippage_pct = 0.0
    risk = RiskManager(config.risk)
    risk.reset_day(config.risk.starting_balance)
    return Engine(config, strategies={"ADA/USDT": Switch()}, risk=risk, execution=PaperExecutionEngine(config),
                  storage=Storage(":memory:"), exchange=exchange, enforce_daily_loss=False)


def _trade(exit_price, stop_price, side=Side.BUY, reason="stop-loss"):
    t = datetime(2026, 10, 7, 2, 0, tzinfo=timezone.utc)
    return ClosedTrade(symbol="ADA/USDT", category="volumen", strategy_name="volume_surge", side=side, amount=100.0,
                       entry_price=1.0, exit_price=exit_price, fee_total=0.1, pnl_abs=-5.0, pnl_pct=-5.0,
                       exit_reason=reason, opened_at=t, closed_at=t, stop_price=stop_price)


# --- Fase 1: medir el deslizamiento ------------------------------------------------------------

def test_stop_exit_records_the_stop_level():
    engine = _engine()
    engine.process("ADA/USDT", _candles(1.00))
    stop = engine.positions[0].stop_loss
    engine.strategies["ADA/USDT"].buy = False
    engine.process("ADA/USDT", _candles(0.92))            # cae un 8%: salta el stop del 5%

    row = engine.storage.all_trades()[0]
    assert row["exit_reason"] == "stop-loss"
    assert row["stop_price"] == pytest.approx(stop)
    assert row["exit_price"] < row["stop_price"]          # vendió por debajo del nivel

    slip = engine.storage.stop_slippage()
    assert slip["stops"] == 1
    assert slip["avg_pct"] == pytest.approx((0.92 / stop - 1) * 100)


def test_take_profit_exit_has_no_stop_level():
    engine = _engine()
    engine.process("ADA/USDT", _candles(1.00))
    engine.strategies["ADA/USDT"].buy = False
    engine.process("ADA/USDT", _candles(1.25))

    row = engine.storage.all_trades()[0]
    assert row["exit_reason"] == "take-profit"
    assert row["stop_price"] is None
    assert engine.storage.stop_slippage()["stops"] == 0


def test_stop_slippage_stats_and_report():
    st = Storage(":memory:")
    st.record_closed_trade(_trade(exit_price=0.94, stop_price=0.95))      # -1,05%
    st.record_closed_trade(_trade(exit_price=0.93, stop_price=0.95))      # -2,11%
    st.record_closed_trade(_trade(exit_price=1.20, stop_price=None, reason="take-profit"))

    slip = st.stop_slippage()
    assert slip["stops"] == 2
    assert slip["avg_pct"] == pytest.approx(((0.94 / 0.95 - 1) + (0.93 / 0.95 - 1)) / 2 * 100)
    assert slip["worst_pct"] == pytest.approx((0.93 / 0.95 - 1) * 100)
    assert "Deslizam. en stops" in render_report(st)


def test_slippage_sign_for_shorts():
    # En un corto el stop está por encima: recomprar más caro que el nivel es peor (negativo).
    assert _trade(exit_price=1.06, stop_price=1.05, side=Side.SELL).stop_slippage_pct < 0
    assert _trade(exit_price=0.94, stop_price=0.95).stop_slippage_pct < 0
    assert _trade(exit_price=1.2, stop_price=None).stop_slippage_pct is None


def test_old_database_gets_the_new_column(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE closed_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL,"
        " category TEXT NOT NULL, strategy TEXT NOT NULL, side TEXT NOT NULL, amount REAL NOT NULL,"
        " entry_price REAL NOT NULL, exit_price REAL NOT NULL, fee_total REAL NOT NULL, pnl_abs REAL NOT NULL,"
        " pnl_pct REAL NOT NULL, exit_reason TEXT NOT NULL, opened_at TEXT NOT NULL, closed_at TEXT NOT NULL,"
        " duration_s REAL NOT NULL)"
    )
    conn.execute(
        "INSERT INTO closed_trades (symbol, category, strategy, side, amount, entry_price, exit_price, fee_total,"
        " pnl_abs, pnl_pct, exit_reason, opened_at, closed_at, duration_s) VALUES"
        " ('DOT/USDT','grid','grid','buy',1,1,0.95,0.1,-5,-5,'stop-loss','2026-10-07T00:00:00+00:00',"
        " '2026-10-07T02:00:00+00:00',7200)"
    )
    conn.commit(); conn.close()

    st = Storage(path)                                     # migra sin perder lo que había
    assert st.trade_count() == 1
    assert st.all_trades()[0]["stop_price"] is None
    assert st.stop_slippage()["stops"] == 0                # los stops antiguos no tienen nivel
    st.record_closed_trade(_trade(exit_price=0.94, stop_price=0.95))
    assert st.stop_slippage()["stops"] == 1
    st.close()


# --- Fase 2: sondeo rápido ---------------------------------------------------------------------

def test_fast_poll_closes_position_below_stop_without_counting_a_bar():
    exchange = FakeExchange({"ADA/USDT": 0.99})
    engine = _engine(exchange)
    engine.process("ADA/USDT", _candles(1.00))
    bars = engine.positions[0].bars_held

    _poll_open_exits(engine, {})                           # precio dentro de rango: no pasa nada
    assert len(engine.positions) == 1
    assert engine.positions[0].bars_held == bars
    assert engine.last_prices["ADA/USDT"] == 0.99

    exchange.prices["ADA/USDT"] = 0.94                     # perfora el stop del 5%
    _poll_open_exits(engine, {})
    assert engine.positions == []
    assert engine.storage.all_trades()[0]["exit_reason"] == "stop-loss"
    assert exchange.calls == [["ADA/USDT"], ["ADA/USDT"]]  # una consulta por sondeo


def test_fast_poll_skips_symbols_without_price_and_does_nothing_when_flat():
    exchange = FakeExchange({})
    engine = _engine(exchange)
    _poll_open_exits(engine, {})
    assert exchange.calls == []                            # sin posiciones no consulta

    engine.process("ADA/USDT", _candles(1.00))
    _poll_open_exits(engine, {})                           # el exchange no devuelve precio
    assert len(engine.positions) == 1


def test_wait_cycle_polls_only_while_there_are_positions():
    exchange = FakeExchange({"ADA/USDT": 1.0})
    engine = _engine(exchange)
    clock = FakeClock()

    _wait_cycle(engine, 60, 10, {}, sleep=clock.sleep, clock=clock.clock)
    assert clock.sleeps == [60] and exchange.calls == []   # sin posiciones: duerme de un tirón

    engine.process("ADA/USDT", _candles(1.00))
    clock = FakeClock()
    _wait_cycle(engine, 60, 10, {}, sleep=clock.sleep, clock=clock.clock)
    assert clock.sleeps == [10] * 6
    assert len(exchange.calls) == 5                        # a los 10, 20, 30, 40 y 50 s; a los 60 ya toca el ciclo


def test_wait_cycle_stops_polling_once_the_position_is_closed():
    exchange = FakeExchange({"ADA/USDT": 0.90})
    engine = _engine(exchange)
    engine.process("ADA/USDT", _candles(1.00))
    clock = FakeClock()

    _wait_cycle(engine, 60, 10, {}, sleep=clock.sleep, clock=clock.clock)
    assert engine.positions == []                          # cerrada en el primer sondeo
    assert clock.sleeps == [10, 50]
    assert len(exchange.calls) == 1


def test_wait_cycle_disabled_or_failing_never_breaks_the_loop():
    engine = _engine(FakeExchange(fail=True))
    engine.process("ADA/USDT", _candles(1.00))

    clock = FakeClock()
    _wait_cycle(engine, 60, 0, {}, sleep=clock.sleep, clock=clock.clock)
    assert clock.sleeps == [60]                            # desactivado: como siempre

    clock = FakeClock()
    _wait_cycle(engine, 60, 10, {}, sleep=clock.sleep, clock=clock.clock)
    assert clock.sleeps == [10, 50]                        # falla el sondeo: espera el resto del ciclo
    assert len(engine.positions) == 1


def test_exchange_fetch_last_prices_single_request():
    class Client:
        def __init__(self):
            self.calls = []

        def fetch_tickers(self, symbols):
            self.calls.append(symbols)
            return {"ADA/USDT": {"last": 0.27}, "DOT/USDT": {"last": None, "close": 1.1}, "NEW/USDT": {}}

    ex = Exchange.__new__(Exchange)
    ex.config = Config()
    ex._client = Client()

    prices = ex.fetch_last_prices(["ADA/USDT", "DOT/USDT", "NEW/USDT"])
    assert prices == {"ADA/USDT": 0.27, "DOT/USDT": 1.1}   # sin precio -> se omite
    assert len(ex._client.calls) == 1
    assert ex.fetch_last_prices([]) == {}
