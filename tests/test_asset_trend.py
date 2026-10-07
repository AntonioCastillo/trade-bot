"""Filtro de tendencia de la propia moneda: la cabeza solo entra si el precio está
en o por encima de su EMA diaria de N velas."""

import pandas as pd
import pytest
from conftest import make_instrument

from tradebot.config import Config, RiskConfig, _build_instruments
from tradebot.engine import Engine
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.models import Signal, SignalType
from tradebot.regime import is_above_daily_ema, is_btc_macro_bullish
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.base import Strategy

UP = [100.0] * 30 + [120.0] * 10        # precio por encima de su media
DOWN = [100.0] * 30 + [80.0] * 10       # precio por debajo


class AlwaysBuy(Strategy):
    def generate_signal(self, symbol, candles):
        return Signal(SignalType.BUY, symbol, float(candles["close"].iloc[-1]))


class DailyExchange:
    """Devuelve velas diarias fijas por símbolo y registra las consultas."""

    def __init__(self, closes_by_symbol, fail=False):
        self.closes, self.fail, self.calls = closes_by_symbol, fail, []

    def fetch_ohlcv(self, symbol, timeframe="1d", limit=200):
        self.calls.append((symbol, timeframe, limit))
        if self.fail:
            raise ConnectionError("sin red")
        return pd.DataFrame({"close": self.closes[symbol]})


def _candles(price: float) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=1, freq="4h", tz="UTC")
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 1.0}, index=idx)


def _engine(exchange, **ins_kw):
    ins = make_instrument(symbol="NEAR/USDT", category="grid", stop_loss_pct=0.05, take_profit_pct=0.10)
    for k, v in ins_kw.items():
        setattr(ins, k, v)
    config = Config(instruments=[ins], risk=RiskConfig(starting_balance=10_000))
    risk = RiskManager(config.risk)
    risk.reset_day(config.risk.starting_balance)
    return Engine(config, strategies={"NEAR/USDT": AlwaysBuy()}, risk=risk,
                  execution=PaperExecutionEngine(config), storage=Storage(":memory:"),
                  exchange=exchange, enforce_daily_loss=False)


def test_is_above_daily_ema():
    assert is_above_daily_ema(DailyExchange({"NEAR/USDT": UP}), "NEAR/USDT", 20) is True
    assert is_above_daily_ema(DailyExchange({"NEAR/USDT": DOWN}), "NEAR/USDT", 20) is False


def test_is_above_daily_ema_never_blocks_without_data():
    assert is_above_daily_ema(None, "NEAR/USDT", 20) is True                              # backtests
    assert is_above_daily_ema(DailyExchange({}, fail=True), "NEAR/USDT", 20) is True      # fallo de red
    assert is_above_daily_ema(DailyExchange({"NEAR/USDT": [1.0] * 5}), "NEAR/USDT", 20) is True   # pocas velas


def test_btc_macro_filter_keeps_working():
    assert is_btc_macro_bullish(DailyExchange({"BTC/USDT": [100.0] * 50 + [150.0] * 10})) is True
    assert is_btc_macro_bullish(DailyExchange({"BTC/USDT": [200.0] * 50 + [100.0] * 10})) is False


def test_entry_blocked_when_asset_is_below_its_ema():
    exchange = DailyExchange({"NEAR/USDT": DOWN})
    engine = _engine(exchange, asset_trend_ema=20)
    engine.process("NEAR/USDT", _candles(80.0))

    assert engine.positions == []
    assert exchange.calls == [("NEAR/USDT", "1d", 50)]     # consulta las velas diarias de la propia moneda


def test_entry_allowed_when_asset_is_above_its_ema():
    engine = _engine(DailyExchange({"NEAR/USDT": UP}), asset_trend_ema=20)
    engine.process("NEAR/USDT", _candles(120.0))

    assert [p.symbol for p in engine.positions] == ["NEAR/USDT"]


def test_filter_disabled_by_default_does_not_query():
    exchange = DailyExchange({"NEAR/USDT": DOWN})
    engine = _engine(exchange)
    engine.process("NEAR/USDT", _candles(80.0))

    assert len(engine.positions) == 1
    assert exchange.calls == []


def test_filter_does_not_affect_exits():
    exchange = DailyExchange({"NEAR/USDT": UP})
    engine = _engine(exchange, asset_trend_ema=20)
    engine.process("NEAR/USDT", _candles(120.0))
    exchange.closes["NEAR/USDT"] = DOWN                    # la tendencia se gira con la posición abierta
    engine.process("NEAR/USDT", _candles(100.0))           # salta el stop del 5%

    assert engine.positions == []                          # cierra, y no reentra
    assert engine.storage.all_trades()[0]["exit_reason"] == "stop-loss"


def test_config_parses_and_validates_asset_trend_ema():
    universe = [
        {"name": "grid", "symbols": ["NEAR/USDT"], "strategy": "grid", "asset_trend_ema": 20},
        {"name": "volumen", "symbols": ["ETH/USDT"], "strategy": "volume_surge"},
    ]
    grid, volumen = _build_instruments(universe, RiskConfig(), "4h")
    assert grid.asset_trend_ema == 20 and volumen.asset_trend_ema == 0

    grid.asset_trend_ema = -5
    with pytest.raises(ValueError, match="asset_trend_ema"):
        Config(instruments=[grid, volumen]).validate()
