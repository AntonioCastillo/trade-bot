"""Señales de un exchange y ejecución en otro (`data_exchange`), y soporte de OKX Europa.

En un exchange con poco volumen, las cabezas que miran el volumen ven picos donde no los hay.
Por eso las velas de las señales pueden salir de un mercado líquido (solo datos públicos)
mientras las órdenes, los saldos y los precios de las salidas siguen en el exchange que opera.
"""

from unittest.mock import MagicMock

import ccxt
import pandas as pd
import pytest
from conftest import make_instrument

from tradebot.config import Config, Credentials, RiskConfig, credential_env_names, load_config
from tradebot.daemon import _execution_prices
from tradebot.engine import Engine
from tradebot.exchange import Exchange
from tradebot.exchange_stops import CLIENT_PREFIX, StopGuard
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.models import Position, Side, Signal, SignalType
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.base import Strategy

SYMBOL = "NEAR/USDC"
YAML = """
mode: paper
exchange: {exchange}
{extra}
universe:
  - name: grid
    symbols: [NEAR/USDC]
    strategy: grid
risk:
  quote_currency: USDC
"""


def _load(tmp_path, monkeypatch, exchange="myokx", extra="", env=None):
    monkeypatch.setattr("tradebot.config.load_dotenv", lambda *a, **k: None)
    for name in ("OKX_API_KEY", "OKX_API_SECRET", "OKX_API_PASSPHRASE", "BYBIT_API_KEY", "BYBIT_API_SECRET"):
        monkeypatch.delenv(name, raising=False)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)
    path = tmp_path / "cfg.yaml"
    path.write_text(YAML.format(exchange=exchange, extra=extra), encoding="utf-8")
    return load_config(path)


# --- configuración --------------------------------------------------------------------------------

def test_signal_source_is_optional_and_maps_the_quote(tmp_path, monkeypatch):
    plain = _load(tmp_path, monkeypatch, exchange="bybiteu")
    assert plain.signals_elsewhere is False and plain.data_symbol(SYMBOL) == SYMBOL

    config = _load(tmp_path, monkeypatch, extra="data_exchange: binance\ndata_quote: USDT")
    assert config.signals_elsewhere is True
    assert config.data_symbol(SYMBOL) == "NEAR/USDT" and config.data_symbol(config.reference_symbol) == "BTC/USDT"

    same = _load(tmp_path, monkeypatch, extra="data_exchange: myokx")     # el mismo exchange: nada cambia
    assert same.signals_elsewhere is False


def test_okx_needs_key_secret_and_passphrase(tmp_path, monkeypatch):
    assert credential_env_names("myokx") == ["OKX_API_KEY", "OKX_API_SECRET", "OKX_API_PASSPHRASE"]
    config = _load(tmp_path, monkeypatch, env={"OKX_API_KEY": "k", "OKX_API_SECRET": "s"})
    assert config.credentials.is_complete is False                        # falta la passphrase
    config = _load(tmp_path, monkeypatch, env={"OKX_API_KEY": "k", "OKX_API_SECRET": "s", "OKX_API_PASSPHRASE": "p"})
    assert config.credentials.is_complete and config.exchange_name == "OKX Europa"


# --- velas de la fuente de señales; todo lo demás, del exchange que opera ------------------------

def _candles(n=3, price=5.0):
    return [[1_700_000_000_000 + i * 900_000, price, price, price, price, 10.0] for i in range(n)]


def _exchange(monkeypatch, data_exchange="binance"):
    built = {}

    class Client:
        def __init__(self, params):
            self.params = params
            self.fetch_ohlcv = MagicMock(return_value=_candles())
            self.parse_timeframe = lambda tf: 900
            self.milliseconds = lambda: 1_700_000_000_000 + 3 * 900_000
            self.load_time_difference = lambda: None

    for name in ("myokx", "binance", "bybiteu"):
        monkeypatch.setattr(ccxt, name, type(name, (Client,), {"__init__": lambda self, p, n=name: (Client.__init__(self, p), built.setdefault(n, self))[0]}))
    config = Config(exchange="myokx", risk=RiskConfig(quote_currency="USDC"), data_exchange=data_exchange, data_quote="USDT",
                    credentials=Credentials("k", "s", "p"))
    return Exchange(config), built


def test_candles_come_from_the_signal_source_with_its_own_pair(monkeypatch):
    ex, built = _exchange(monkeypatch)

    df = ex.fetch_ohlcv(SYMBOL, "4h", 300)

    built["binance"].fetch_ohlcv.assert_called_once_with("NEAR/USDT", timeframe="4h", limit=300)
    built["myokx"].fetch_ohlcv.assert_not_called()
    assert len(df) == 3
    assert "apiKey" not in built["binance"].params                         # la fuente no usa claves
    assert built["myokx"].params["apiKey"] == "k" and built["myokx"].params["options"]["defaultType"] == "spot"

    ex.fetch_ohlcv_history(SYMBOL, "15m", 3)
    assert built["binance"].fetch_ohlcv.call_args.kwargs["limit"] == 1000   # páginas de Binance, no de OKX


def test_without_signal_source_candles_come_from_the_exchange(monkeypatch):
    ex, built = _exchange(monkeypatch, data_exchange="")
    ex.fetch_ohlcv(SYMBOL, "4h", 300)
    built["myokx"].fetch_ohlcv.assert_called_once_with(SYMBOL, timeframe="4h", limit=300)
    assert "binance" not in built


def test_unknown_signal_source_is_rejected(monkeypatch):
    config = Config(exchange="myokx", risk=RiskConfig(quote_currency="USDC"), data_exchange="noexiste")
    monkeypatch.setattr(ccxt, "myokx", lambda params: MagicMock())
    with pytest.raises(ValueError, match="noexiste"):
        Exchange(config)


class AlwaysBuy(Strategy):
    def generate_signal(self, symbol, candles):
        return Signal(SignalType.BUY, symbol, float(candles["close"].iloc[-1]))


def _engine(elsewhere: bool):
    ins = make_instrument(symbol=SYMBOL, category="grid", stop_loss_pct=0.05, take_profit_pct=0.10)
    config = Config(exchange="myokx", instruments=[ins], risk=RiskConfig(starting_balance=10_000, quote_currency="USDC"),
                    data_exchange="binance" if elsewhere else "", data_quote="USDT")
    risk = RiskManager(config.risk)
    risk.reset_day(config.risk.starting_balance)
    return Engine(config, strategies={SYMBOL: AlwaysBuy()}, risk=risk, execution=PaperExecutionEngine(config),
                  storage=Storage(":memory:"), enforce_daily_loss=False)


def _bar(price):
    idx = pd.date_range("2024-01-01", periods=1, freq="4h", tz="UTC")
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 1.0}, index=idx)


@pytest.mark.parametrize("elsewhere, sold", [(False, True), (True, False)])
def test_exits_are_not_decided_with_the_other_exchange_candles(elsewhere, sold):
    """Con señales de otro exchange, el cierre de su vela no puede provocar un stop aquí."""
    engine = _engine(elsewhere)
    engine.process(SYMBOL, _bar(5.0))
    engine.strategies[SYMBOL] = MagicMock(generate_signal=lambda s, c: Signal(SignalType.HOLD, s, 4.0))
    engine.last_prices[SYMBOL] = 5.0

    engine.process(SYMBOL, _bar(4.0))                                     # vela de la fuente por debajo del stop

    assert (engine.positions == []) is sold
    assert engine.last_prices[SYMBOL] == (4.0 if not elsewhere else 5.0)


def test_cycle_reads_exit_prices_from_the_exchange_that_trades():
    engine = MagicMock()
    engine.exchange.fetch_last_prices.return_value = {SYMBOL: 5.01}
    config = Config(exchange="myokx", risk=RiskConfig(quote_currency="USDC"), data_exchange="binance")

    assert _execution_prices(engine, config, [SYMBOL]) == {SYMBOL: 5.01}
    engine.exchange.fetch_last_prices.side_effect = ConnectionError("sin red")
    assert _execution_prices(engine, config, [SYMBOL]) == {}                # ese ciclo no evalúa salidas
    assert _execution_prices(engine, Config(exchange="bybiteu"), [SYMBOL]) == {}


# --- órdenes de stop en OKX ------------------------------------------------------------------------

def _okx():
    ex = Exchange.__new__(Exchange)
    ex._is_okx = True
    ex._client = MagicMock()
    ex._client.amount_to_precision.side_effect = lambda s, a: f"{a:.4f}"
    ex._client.price_to_precision.side_effect = lambda s, p: f"{p:.4f}"
    ex._normalize_symbol = lambda s: s
    return ex


def test_okx_stop_is_a_conditional_algo_order_with_an_alphanumeric_client_id():
    ex = _okx()
    ex._client.create_order.return_value = {"id": "algo1", "clientOrderId": None, "info": {"algoClOrdId": "tbstopabc"}}
    client_id = CLIENT_PREFIX + "abc"

    order = ex.create_stop_sell(SYMBOL, 21.95, 4.6872, client_id)

    ex._client.create_order.assert_called_once_with(
        SYMBOL, "market", "sell", 21.95, None,
        {"stopLossPrice": 4.6872, "clientOrderId": client_id, "algoClOrdId": client_id})
    assert (order["id"], order["client_id"]) == ("algo1", client_id)
    assert client_id.isalnum()                                              # OKX no admite guiones


def test_okx_lists_conditional_orders_and_reads_their_client_id():
    ex = _okx()
    ex._client.fetch_open_orders.return_value = [
        {"id": "algo1", "clientOrderId": None, "symbol": SYMBOL, "amount": 21.95, "triggerPrice": None, "status": "open",
         "info": {"algoClOrdId": "tbstopabc", "slTriggerPx": "4.6872"}},
    ]

    orders = ex.fetch_open_stop_orders()

    ex._client.fetch_open_orders.assert_called_once_with(None, None, 100, {"trigger": True, "ordType": "conditional"})
    assert orders[0]["client_id"] == "tbstopabc"


@pytest.mark.parametrize("code, msg, expected", [
    ("0", "", True),
    ("51400", "Cancellation failed as the order does not exist", False),
    ("51402", "Order has been completed", False),
    ("50001", "Service temporarily unavailable", "raise"),
])
def test_okx_cancel_reads_the_result_inside_the_response(code, msg, expected):
    ex = _okx()
    ex._client.cancel_order.return_value = {"id": "algo1", "info": {"algoId": "algo1", "sCode": code, "sMsg": msg}}

    if expected == "raise":
        with pytest.raises(ccxt.ExchangeError, match=code):
            ex.cancel_stop_order("algo1", SYMBOL)
    else:
        assert ex.cancel_stop_order("algo1", SYMBOL) is expected
    ex._client.cancel_order.assert_called_with("algo1", SYMBOL, {"trigger": True})


def test_old_and_new_client_ids_are_both_recognised():
    guard = StopGuard(MagicMock())
    guard.exchange.fetch_open_stop_orders.return_value = [
        {"id": "a", "client_id": "tbstop-0123", "symbol": SYMBOL},            # creada por una versión anterior
        {"id": "b", "client_id": "tbstop4567", "symbol": SYMBOL},
        {"id": "c", "client_id": "manual", "symbol": SYMBOL},
    ]
    assert set(guard.open_orders()) == {"a", "b"}


def test_position_gone_uses_the_total_balance():
    """Si el exchange bloquea el saldo mientras vive la orden de stop, el libre sale a 0
    aunque la moneda siga en la cuenta: no debe darse la posición por vendida."""
    exchange = MagicMock()
    exchange.fetch_balance.return_value = 0.0                               # libre
    exchange.fetch_balances_total.return_value = {"NEAR": 21.95}            # total
    guard = StopGuard(exchange)
    pos = Position(symbol=SYMBOL, side=Side.BUY, amount=21.95, entry_price=5.0, stop_loss=4.78, take_profit=5.15)

    assert guard.position_gone(pos) is False
    exchange.fetch_balances_total.return_value = {}
    assert guard.position_gone(pos) is True
