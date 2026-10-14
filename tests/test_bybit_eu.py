"""Exchange configurable: KuCoin (el de siempre) o Bybit EU. Claves por exchange, moneda de
cotización, llamadas propias de Bybit y comisiones cobradas en la moneda comprada."""

from dataclasses import asdict
from unittest.mock import MagicMock

import ccxt
import pandas as pd
import pytest
from conftest import make_instrument

from tradebot.config import Config, Credentials, RiskConfig, credential_env_names, load_config
from tradebot.daemon import _adopt_positions
from tradebot.engine import Engine, ForeignPositionsError
from tradebot.exchange import Exchange
from tradebot.execution.live import LiveExecutionEngine
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.models import Order, Side, Signal, SignalType
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.base import Strategy

SYMBOL = "ADA/USDC"
ENV = ("KUCOIN_API_KEY", "KUCOIN_API_SECRET", "KUCOIN_API_PASSPHRASE", "BYBIT_API_KEY", "BYBIT_API_SECRET")
YAML = """
mode: {mode}
exchange: {exchange}
universe:
  - name: grid
    symbols: [{symbol}]
    strategy: grid
risk:
  quote_currency: {quote}
"""


def _load(tmp_path, monkeypatch, env=None, **kw):
    """Carga una configuración mínima con SOLO las claves indicadas en el entorno."""
    monkeypatch.setattr("tradebot.config.load_dotenv", lambda *a, **k: None)
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)
    values = dict(mode="paper", exchange="bybiteu", symbol="NEAR/USDC", quote="USDC")
    values.update(kw)
    path = tmp_path / "cfg.yaml"
    path.write_text(YAML.format(**values), encoding="utf-8")
    return load_config(path)


# --- configuración ------------------------------------------------------------------------------

def test_bybit_reads_its_own_keys_and_needs_no_passphrase(tmp_path, monkeypatch):
    env = {"BYBIT_API_KEY": "k", "BYBIT_API_SECRET": "s", "KUCOIN_API_KEY": "otra", "KUCOIN_API_PASSPHRASE": "p"}
    config = _load(tmp_path, monkeypatch, env, mode="live")

    assert (config.credentials.api_key, config.credentials.api_secret, config.credentials.api_passphrase) == ("k", "s", "")
    assert config.credentials.is_complete
    assert (config.exchange_name, config.reference_symbol) == ("Bybit EU", "BTC/USDC")


def test_kucoin_still_needs_its_passphrase(tmp_path, monkeypatch):
    env = {"KUCOIN_API_KEY": "k", "KUCOIN_API_SECRET": "s", "BYBIT_API_KEY": "otra", "BYBIT_API_SECRET": "otra"}
    with pytest.raises(ValueError, match="KUCOIN_API_PASSPHRASE"):
        _load(tmp_path, monkeypatch, env, mode="live", exchange="kucoin", symbol="NEAR/USDT", quote="USDT")

    config = _load(tmp_path, monkeypatch, dict(env, KUCOIN_API_PASSPHRASE="p"),
                   mode="live", exchange="kucoin", symbol="NEAR/USDT", quote="USDT")
    assert config.credentials.is_complete and config.credentials.api_passphrase == "p"
    assert (config.exchange_name, config.reference_symbol) == ("KuCoin", "BTC/USDT")
    assert Credentials("k", "s").is_complete is False            # por defecto se exige passphrase


def test_live_without_bybit_keys_names_the_missing_variables(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="BYBIT_API_KEY, BYBIT_API_SECRET"):
        _load(tmp_path, monkeypatch, {"KUCOIN_API_KEY": "k", "KUCOIN_API_SECRET": "s", "KUCOIN_API_PASSPHRASE": "p"}, mode="live")
    assert credential_env_names("bybiteu") == ["BYBIT_API_KEY", "BYBIT_API_SECRET"]
    assert credential_env_names("kucoin") == ["KUCOIN_API_KEY", "KUCOIN_API_SECRET", "KUCOIN_API_PASSPHRASE"]


def test_unknown_exchange_is_rejected(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="exchange no admitido"):
        _load(tmp_path, monkeypatch, exchange="binance")


def test_symbols_in_another_quote_currency_are_rejected(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="NEAR/USDT"):
        _load(tmp_path, monkeypatch, symbol="NEAR/USDT")          # config a medio migrar


def test_live_config_runs_on_bybit_eu(monkeypatch):
    """config.yaml opera en Bybit EU desde la migración: USDC, sin ETC, su comisión y sus stops."""
    monkeypatch.setattr("tradebot.config.load_dotenv", lambda *a, **k: None)
    for name in ENV:
        monkeypatch.setenv(name, "x")
    config = load_config("config.yaml")

    assert (config.mode, config.exchange, config.risk.quote_currency) == ("live", "bybiteu", "USDC")
    assert config.symbols() and all(s.endswith("/USDC") for s in config.symbols())
    assert not any(s.startswith("ETC/") for s in config.symbols())
    assert (config.engine.fee_pct, config.engine.exchange_stops) == (0.0025, True)
    assert config.carry.funding_radar_enabled is False             # el radar mira los futuros de KuCoin
    assert config.credentials.is_complete and config.credentials.api_passphrase == ""


# --- cliente de ccxt ----------------------------------------------------------------------------

def _client_params(monkeypatch, exchange, credentials):
    seen = {}

    class FakeClient:
        def __init__(self, params):
            seen.update(params)

        def load_time_difference(self):
            seen["time_loaded"] = True

    monkeypatch.setattr(ccxt, exchange, FakeClient)
    ex = Exchange(Config(exchange=exchange, credentials=credentials))
    return ex, seen


def test_bybit_client_is_spot_and_has_no_password(monkeypatch):
    ex, params = _client_params(monkeypatch, "bybiteu", Credentials("k", "s", needs_passphrase=False))

    assert params["options"] == {"adjustForTimeDifference": True, "defaultType": "spot"}
    assert (params["apiKey"], params["secret"]) == ("k", "s") and "password" not in params
    assert params["time_loaded"] is True
    assert ex._ohlcv_page == 1000


def test_kucoin_client_is_built_as_before(monkeypatch):
    ex, params = _client_params(monkeypatch, "kucoin", Credentials("k", "s", "p"))

    assert params["options"] == {"adjustForTimeDifference": True}
    assert (params["apiKey"], params["secret"], params["password"]) == ("k", "s", "p")
    assert ex._ohlcv_page == 1500


def test_client_without_keys_sends_none(monkeypatch):
    _, params = _client_params(monkeypatch, "bybiteu", Credentials(needs_passphrase=False))
    assert "apiKey" not in params and "time_loaded" not in params


# --- llamadas propias de Bybit ------------------------------------------------------------------

def _bybit():
    ex = Exchange.__new__(Exchange)
    ex._is_bybit = True
    ex._client = MagicMock()
    ex._client.amount_to_precision.side_effect = lambda s, a: f"{a:.4f}"
    ex._client.price_to_precision.side_effect = lambda s, p: f"{p:.5f}"
    ex._normalize_symbol = lambda s: s
    return ex


def test_bybit_stop_is_a_conditional_order_not_a_tpsl_one():
    """`triggerPrice` crea la orden condicional (no bloquea saldo, como en KuCoin);
    `stopLossPrice` crearía la de TP/SL, que sí lo bloquea y rompería las ventas del bot."""
    ex = _bybit()
    ex._client.create_order.return_value = {"id": "abc", "info": {}}

    order = ex.create_stop_sell(SYMBOL, 123.456789, 0.2512349, "tbstop-1")

    ex._client.create_order.assert_called_once_with(SYMBOL, "market", "sell", 123.4568, None,
                                                    {"triggerPrice": 0.25123, "clientOrderId": "tbstop-1"})
    assert (order["id"], order["client_id"], order["trigger_price"]) == ("abc", "tbstop-1", 0.25123)


def test_bybit_lists_and_cancels_stop_orders():
    ex = _bybit()
    ex._client.fetch_open_orders.return_value = [
        {"id": "abc", "clientOrderId": None, "symbol": SYMBOL, "amount": 10.0, "triggerPrice": 0.25, "status": "open",
         "info": {"orderLinkId": "tbstop-1"}},
    ]

    orders = ex.fetch_open_stop_orders()

    ex._client.fetch_open_orders.assert_called_once_with(None, None, 50, {"trigger": True})
    assert orders == [{"id": "abc", "client_id": "tbstop-1", "symbol": SYMBOL, "amount": 10.0, "trigger_price": 0.25, "status": "open"}]

    assert ex.cancel_stop_order("abc", SYMBOL) is True
    ex._client.cancel_order.assert_called_once_with("abc", SYMBOL, {"trigger": True})
    ex._client.cancel_order.side_effect = ccxt.OrderNotFound("Order does not exist")
    assert ex.cancel_stop_order("abc", SYMBOL) is False


def test_bybit_order_lookup_acknowledges_and_falls_back_to_history():
    ex = _bybit()
    ex._client.fetch_order.return_value = {"id": "o1", "filled": 5.0}

    assert ex.fetch_order_fill("o1", SYMBOL) == {"id": "o1", "filled": 5.0}
    ex._client.fetch_order.assert_called_once_with("o1", SYMBOL, {"acknowledged": True})

    ex._client.fetch_order.side_effect = ccxt.OrderNotFound("ya no está entre las recientes")
    ex._client.fetch_closed_order.return_value = {"id": "o1", "filled": 7.0}
    assert ex.fetch_order_fill("o1", SYMBOL) == {"id": "o1", "filled": 7.0}
    ex._client.fetch_closed_order.assert_called_once_with("o1", SYMBOL)


def test_kucoin_order_lookup_is_unchanged():
    ex = _bybit()
    ex._is_bybit = False
    ex._client.fetch_order.return_value = {"id": "o1", "filled": 0}

    assert ex.fetch_order_fill("o1", SYMBOL) is None
    ex._client.fetch_order.assert_called_once_with("o1", SYMBOL)


def test_history_pages_respect_the_exchange_limit():
    ex = _bybit()
    ex._ohlcv_page = 1000
    ex._client.parse_timeframe.return_value = 3600
    ex._client.milliseconds.return_value = 10_000 * 3_600_000
    ex._client.fetch_ohlcv.side_effect = lambda s, tf, since, limit: [[since + i * 3_600_000, 1, 1, 1, 1, 1] for i in range(limit)]

    candles = ex.fetch_ohlcv_history(SYMBOL, "1h", 1500)

    assert len(candles) == 1500
    assert {c.kwargs["limit"] for c in ex._client.fetch_ohlcv.call_args_list} == {1000}


# --- comisión cobrada en la moneda comprada -----------------------------------------------------

def _live():
    config = Config(exchange="bybiteu", risk=RiskConfig(quote_currency="USDC"))
    return LiveExecutionEngine(config, MagicMock())


def test_buy_fee_charged_in_the_bought_coin_is_netted_and_converted():
    """Bybit cobra la comisión de las compras en la moneda comprada: llega menos cantidad."""
    order = Order(SYMBOL, Side.BUY, 1000.0, 0.25)
    result = {"id": "o1", "filled": 1000.0, "average": 0.25, "fee": {"cost": 1.0, "currency": "ADA"}}

    fill = _live()._to_fill(order, result)

    assert fill.confirmed is True
    assert fill.filled_amount == pytest.approx(999.0)             # lo que hay de verdad en la cuenta
    assert fill.fee == pytest.approx(0.25)                        # 1 ADA a 0,25 = 0,25 USDC
    # Coste real 250 USDC por 999 ADA: precio*cantidad + comisión lo reproduce.
    assert fill.filled_price * fill.filled_amount + fill.fee == pytest.approx(250.0)


def test_sell_fee_in_quote_currency_is_left_alone():
    order = Order(SYMBOL, Side.SELL, 999.0, 0.30)
    result = {"id": "o2", "filled": 999.0, "average": 0.30, "fee": {"cost": 0.2997, "currency": "USDC"}}

    fill = _live()._to_fill(order, result)

    assert (fill.filled_amount, fill.fee) == (999.0, 0.2997)

    odd = {"id": "o3", "filled": 999.0, "average": 0.30, "fee": {"cost": 1.0, "currency": "ADA"}}
    assert _live()._to_fill(order, odd).filled_amount == 999.0     # en una venta nunca se toca la cantidad


def test_late_confirmation_also_nets_the_fee():
    engine = _live()
    order = Order(SYMBOL, Side.BUY, 1000.0, 0.25)
    estimated = engine._to_fill(order, {"id": "o1"})                 # el exchange aún no dio la ejecución
    engine.exchange.fetch_order_fill.return_value = {"filled": 1000.0, "average": 0.26, "fee": {"cost": 1.0, "currency": "ADA"}}

    real = engine.confirm_fill(estimated)

    assert (real.filled_price, real.confirmed) == (0.26, True)
    assert real.filled_amount == pytest.approx(999.0) and real.fee == pytest.approx(0.26)


# --- el filtro macro mira BTC en la moneda de cotización -----------------------------------------

class AlwaysBuy(Strategy):
    def generate_signal(self, symbol, candles):
        return Signal(SignalType.BUY, symbol, float(candles["close"].iloc[-1]))


class DailyExchange:
    def __init__(self, closes_by_symbol):
        self.closes, self.calls = closes_by_symbol, []

    def fetch_ohlcv(self, symbol, timeframe="1d", limit=200):
        self.calls.append(symbol)
        return pd.DataFrame({"close": self.closes[symbol]})


@pytest.mark.parametrize("btc, opened", [([100.0] * 50 + [150.0] * 10, 1), ([200.0] * 50 + [100.0] * 10, 0)])
def test_macro_filter_uses_btc_in_the_quote_currency(btc, opened):
    ins = make_instrument(symbol="NEAR/USDC", category="grid", stop_loss_pct=0.05, take_profit_pct=0.10)
    ins.macro_btc_filter = True
    config = Config(exchange="bybiteu", instruments=[ins], risk=RiskConfig(starting_balance=10_000, quote_currency="USDC"))
    risk = RiskManager(config.risk)
    risk.reset_day(config.risk.starting_balance)
    exchange = DailyExchange({"BTC/USDC": btc})                    # pedir BTC/USDT daría KeyError
    engine = Engine(config, strategies={"NEAR/USDC": AlwaysBuy()}, risk=risk,
                    execution=PaperExecutionEngine(config), storage=Storage(":memory:"),
                    exchange=exchange, enforce_daily_loss=False)
    idx = pd.date_range("2024-01-01", periods=1, freq="4h", tz="UTC")

    engine.process("NEAR/USDC", pd.DataFrame({"open": 5.0, "high": 5.0, "low": 5.0, "close": 5.0, "volume": 1.0}, index=idx))

    assert exchange.calls == ["BTC/USDC"]
    assert len(engine.positions) == opened


# --- cambio de exchange con posiciones abiertas --------------------------------------------------

def _persisted_engine(tmp_path, mode):
    """Deja una posición de KuCoin (USDT) en la BD y devuelve un motor configurado para Bybit EU."""
    db = tmp_path / "bot.db"
    old = make_instrument(symbol="NEAR/USDT", category="grid", stop_loss_pct=0.05, take_profit_pct=0.10)
    old_cfg = Config(instruments=[old], risk=RiskConfig(starting_balance=10_000))
    risk = RiskManager(old_cfg.risk)
    risk.reset_day(old_cfg.risk.starting_balance)
    first = Engine(old_cfg, strategies={"NEAR/USDT": AlwaysBuy()}, risk=risk, execution=PaperExecutionEngine(old_cfg),
                   storage=Storage(db), enforce_daily_loss=False)
    idx = pd.date_range("2024-01-01", periods=1, freq="4h", tz="UTC")
    first.process("NEAR/USDT", pd.DataFrame({"open": 5.0, "high": 5.0, "low": 5.0, "close": 5.0, "volume": 1.0}, index=idx))
    assert len(first.positions) == 1
    first.storage.close()

    new = make_instrument(symbol="NEAR/USDC", category="grid", stop_loss_pct=0.05, take_profit_pct=0.10)
    new_cfg = Config(mode=mode, exchange="bybiteu", instruments=[new], risk=RiskConfig(starting_balance=10_000, quote_currency="USDC"))
    exchange = MagicMock()
    engine = Engine(new_cfg, strategies={"NEAR/USDC": AlwaysBuy()}, risk=RiskManager(new_cfg.risk),
                    execution=PaperExecutionEngine(new_cfg), storage=Storage(db), exchange=exchange, enforce_daily_loss=False)
    return engine, exchange


def test_live_refuses_to_start_with_positions_from_the_other_exchange(tmp_path):
    engine, exchange = _persisted_engine(tmp_path, "live")

    with pytest.raises(ForeignPositionsError, match="NEAR/USDT"):
        _adopt_positions(engine)                                    # el arranque NO se lo traga

    assert engine.positions == []
    assert len(engine.storage.load_open_positions()) == 1          # no se toca el registro
    exchange.fetch_balance.assert_not_called()                      # ni se reconcilia contra la cuenta nueva
    exchange.fetch_balances_total.assert_not_called()


def test_other_failures_while_adopting_positions_do_not_stop_the_start():
    engine = MagicMock()
    engine.load_positions.side_effect = ConnectionError("sin red")
    _adopt_positions(engine)                                        # se registra y el bot arranca


def test_paper_ignores_the_quote_check(tmp_path):
    engine, _ = _persisted_engine(tmp_path, "paper")
    assert engine.load_positions() == 1
