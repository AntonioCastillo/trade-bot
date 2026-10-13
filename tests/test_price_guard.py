"""Protección ante precios que no existieron en el mercado (incidente del 2026-10-13):
el bot vendió ADA y AVAX como «toma parcial» con el precio un 5-8% por encima del real.

  - `ticker_price`: un último precio fuera de la horquilla del propio ticker no se usa;
  - `Engine._exit_confirmed`: antes de vender, el libro de órdenes debe respaldar el precio;
  - aviso si una posición lleva un rato sin poder poner su stop en el exchange.
"""

import logging
from unittest.mock import MagicMock

import ccxt
import pandas as pd
import pytest
from conftest import make_instrument

from tradebot import exchange_stops
from tradebot.config import Config, RiskConfig
from tradebot.engine import UNPROTECTED_ALERT_SECONDS, Engine
from tradebot.exchange import Exchange, ticker_price
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.models import Signal, SignalType
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.base import Strategy

SYMBOL = "ADA/USDT"


# --- precio de un ticker ------------------------------------------------------------------------

def test_last_price_inside_the_book_is_trusted():
    assert ticker_price({"last": 0.2355, "bid": 0.2354, "ask": 0.2356}) == (0.2355, True)
    # La última operación puede quedar algo fuera de la horquilla actual: dentro del margen vale.
    assert ticker_price({"last": 0.2370, "bid": 0.2354, "ask": 0.2356}) == (0.2370, True)


def test_last_price_far_from_the_book_is_replaced_by_the_mid():
    price, trusted = ticker_price({"last": 0.2439, "bid": 0.2355, "ask": 0.2357})
    assert trusted is False and price == pytest.approx(0.2356)
    price, trusted = ticker_price({"last": 0.2200, "bid": 0.2355, "ask": 0.2357})      # también por abajo
    assert trusted is False and price == pytest.approx(0.2356)


def test_ticker_without_a_usable_book_keeps_the_old_behaviour():
    assert ticker_price({"last": 0.2439}) == (0.2439, True)
    assert ticker_price({"last": None, "close": 0.2439, "bid": None, "ask": None}) == (0.2439, True)
    assert ticker_price({"last": 0.2439, "bid": 0.2360, "ask": 0.2350}) == (0.2439, True)   # libro cruzado: no sirve de contraste
    assert ticker_price({"last": None, "bid": 0.2355, "ask": 0.2357}) == (0.2355, True)      # recién listada: mejor compra
    assert ticker_price({"last": None, "bid": None, "ask": 0.2357}) == (0.2357, True)
    assert ticker_price({}) == (None, True)


def test_ccxt_invents_the_last_price_and_the_guard_rejects_it():
    """El mecanismo del incidente: KuCoin manda un ticker sin `last` y ccxt lo deduce de la
    media del día anterior y la variación de 24 h. Valores como los de ADA el 13-oct a las 09:28."""
    raw = {"symbol": "ADA-USDT", "buy": "0.2355", "sell": "0.2356", "last": None, "open": "0.2513",
           "changePrice": "-0.0158", "changeRate": "-0.0629", "averagePrice": "0.2518", "high": "0.2538", "low": "0.2244"}
    parsed = ccxt.kucoin().parse_spot_or_uta_ticker(raw)

    assert parsed["last"] == pytest.approx(0.2439)            # un precio al que no se negoció en todo el día
    price, trusted = ticker_price(parsed)
    assert trusted is False and price == pytest.approx(0.23555)


# --- consultas al exchange ----------------------------------------------------------------------

def _wrapper():
    ex = Exchange.__new__(Exchange)
    ex._client = MagicMock()
    ex._normalize_symbol = lambda s: s
    return ex


def test_fast_poll_skips_symbols_with_a_suspect_price(caplog):
    ex = _wrapper()
    ex._client.fetch_tickers.return_value = {
        "ADA/USDT": {"last": 0.2439, "bid": 0.2355, "ask": 0.2357},
        "ETH/USDT": {"last": 2500.0, "bid": 2499.9, "ask": 2500.1},
    }
    with caplog.at_level(logging.WARNING):
        prices = ex.fetch_last_prices(["ADA/USDT", "ETH/USDT"])
        again = ex.fetch_last_prices(["ADA/USDT", "ETH/USDT"])

    assert prices == again == {"ETH/USDT": 2500.0}            # sin precio de ADA no se decide nada sobre ADA
    warnings = [r.getMessage() for r in caplog.records if "fuera de su horquilla" in r.getMessage()]
    assert len(warnings) == 1 and "0.2439" in warnings[0]     # un aviso, no uno cada 10 segundos


def test_single_price_falls_back_to_the_book_mid():
    ex = _wrapper()
    ex._client.fetch_ticker.return_value = {"last": 0.2439, "bid": 0.2355, "ask": 0.2357}
    assert Exchange.fetch_last_price.__wrapped__(ex, "ADA/USDT") == pytest.approx(0.2356)

    ex._client.fetch_ticker.return_value = {"last": 0.2355, "bid": 0.2354, "ask": 0.2356}
    assert Exchange.fetch_last_price.__wrapped__(ex, "ADA/USDT") == 0.2355

    ex._client.fetch_ticker.return_value = {}
    with pytest.raises(ValueError):
        Exchange.fetch_last_price.__wrapped__(ex, "ADA/USDT")


def test_book_price_is_the_best_bid_to_sell_and_the_best_ask_to_buy():
    ex = _wrapper()
    ex._client.fetch_order_book.return_value = {"bids": [[0.2355, 700.0], [0.2354, 10.0]], "asks": [[0.2357, 5.0]]}

    assert ex.fetch_book_price("ADA/USDT", "sell") == 0.2355
    assert ex.fetch_book_price("ADA/USDT", "buy") == 0.2357
    ex._client.fetch_order_book.assert_called_with("ADA/USDT", 20)

    ex._client.fetch_order_book.return_value = {"bids": [], "asks": []}
    with pytest.raises(ValueError):
        ex.fetch_book_price("ADA/USDT", "sell")


# --- confirmación antes de vender ---------------------------------------------------------------

class Switch(Strategy):
    def __init__(self):
        self.buy = True

    def generate_signal(self, symbol, candles):
        price = float(candles["close"].iloc[-1])
        return Signal(SignalType.BUY if self.buy else SignalType.HOLD, symbol, price)


class Book:
    """Exchange de mentira que solo sabe decir a cuánto está el libro."""

    def __init__(self, bid=None, fail=False):
        self.bid, self.fail, self.calls = bid, fail, []

    def fetch_book_price(self, symbol, side):
        self.calls.append((symbol, side))
        if self.fail:
            raise ConnectionError("sin red")
        return self.bid

    def fetch_last_prices(self, symbols):
        return {}


def _candles(price: float) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=1, freq="4h", tz="UTC")
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 1.0}, index=idx)


def _engine(exchange, mode="live"):
    """Posición abierta a 1.00: stop 0.95, arrastre 8%, toma parcial a +5%, objetivo a +20%."""
    ins = make_instrument(symbol=SYMBOL, category="volumen", stop_loss_pct=0.05, take_profit_pct=0.20, trailing_stop_pct=0.08)
    ins.partial_take_profit_pct = 0.05
    config = Config(mode=mode, instruments=[ins], risk=RiskConfig(starting_balance=10_000))
    config.engine.fee_pct, config.engine.slippage_pct = 0.001, 0.0
    risk = RiskManager(config.risk)
    risk.reset_day(config.risk.starting_balance)
    engine = Engine(config, strategies={SYMBOL: Switch()}, risk=risk, execution=PaperExecutionEngine(config),
                    storage=Storage(":memory:"), exchange=exchange, enforce_daily_loss=False)
    engine.process(SYMBOL, _candles(1.00))
    engine.strategies[SYMBOL].buy = False
    assert len(engine.positions) == 1
    return engine


def _poll(engine, price):
    """Lo que hace el sondeo rápido con el precio que le llega."""
    engine._check_exits(SYMBOL, price, count_bar=False)


def test_phantom_high_price_does_not_sell_nor_move_the_stop(caplog):
    """El incidente: el precio «visto» pide toma parcial, pero el mercado sigue en 1.00."""
    book = Book(bid=1.00)
    engine = _engine(book)
    pos = engine.positions[0]
    amount, stop = pos.amount, pos.stop_loss

    with caplog.at_level(logging.WARNING):
        _poll(engine, 1.06)

    assert engine.positions == [pos] and engine.closed_trades == []
    assert pos.amount == amount and pos.partial_tp_done is False
    assert (pos.stop_loss, pos.peak_price) == (stop, 1.00)        # el precio falso tampoco arrastra el stop
    assert book.calls == [(SYMBOL, "sell")]
    assert any("NO confirmada" in r.getMessage() and "1.060000" in r.getMessage() for r in caplog.records)

    _poll(engine, 1.00)                                           # la lectura siguiente, ya correcta: no pasa nada
    assert pos.amount == amount and len(book.calls) == 1


def test_real_partial_take_profit_is_confirmed_and_logged(caplog):
    book = Book(bid=1.058)
    engine = _engine(book)
    pos = engine.positions[0]
    amount = pos.amount

    with caplog.at_level(logging.INFO):
        _poll(engine, 1.06)

    assert pos.amount == pytest.approx(amount / 2) and pos.partial_tp_done is True
    assert pos.stop_loss == pytest.approx(pos.entry_price)
    assert any("precio visto 1.060000, libro 1.058000" in r.getMessage() for r in caplog.records)


def test_phantom_low_price_does_not_trigger_the_stop():
    book = Book(bid=1.00)
    engine = _engine(book)

    _poll(engine, 0.90)                                           # «visto» por debajo del stop; el libro sigue en 1.00

    assert len(engine.positions) == 1 and engine.closed_trades == []


@pytest.mark.parametrize("bid", [0.945, 0.94, 0.80])              # algo por encima, igual, o desplomado
def test_real_stop_sells_wherever_the_book_is_at_or_below_the_price(bid):
    engine = _engine(Book(bid=bid))

    _poll(engine, 0.94)

    assert engine.positions == []
    assert engine.closed_trades[0].exit_reason == "trailing-stop"


def test_real_take_profit_is_confirmed():
    engine = _engine(Book(bid=1.21))
    engine.positions[0].partial_tp_done = True

    _poll(engine, 1.21)

    assert engine.positions == [] and engine.closed_trades[0].exit_reason == "take-profit"


def test_if_the_book_cannot_be_read_a_stop_still_sells_and_the_rest_waits():
    engine = _engine(Book(fail=True))
    amount = engine.positions[0].amount

    _poll(engine, 1.06)                                           # toma parcial: espera
    assert engine.positions[0].amount == amount and engine.closed_trades == []

    _poll(engine, 0.94)                                           # stop: lo urgente es salir
    assert engine.positions == [] and len(engine.closed_trades) == 1


def test_paper_mode_never_asks_the_book():
    book = Book(bid=1.00)
    engine = _engine(book, mode="paper")

    _poll(engine, 1.06)

    assert engine.positions[0].partial_tp_done is True and book.calls == []


def test_exchange_without_a_book_keeps_selling_as_before():
    class NoBook:
        def fetch_last_prices(self, symbols):
            return {}

    engine = _engine(NoBook())
    _poll(engine, 0.94)
    assert engine.positions == []


# --- aviso: posición sin stop en el exchange -----------------------------------------------------

class RejectingExchange:
    """Como KuCoin el 13-oct de 11:20 a 15:28: rechaza crear órdenes de stop."""

    def __init__(self):
        self.reject, self.created = True, 0

    def create_stop_sell(self, symbol, amount, trigger_price, client_id):
        if self.reject:
            raise RuntimeError('kucoin {"msg":"ULTRA-OPEN-SERVICE ERROR.","code":"123002"}')
        self.created += 1
        return dict(id=f"s{self.created}", client_id=client_id, symbol=symbol, amount=amount, trigger_price=trigger_price)

    def fetch_open_stop_orders(self):
        return []

    def cancel_stop_order(self, order_id, symbol):
        return True

    def fetch_balance(self, currency):
        return 1_000_000.0

    def fetch_last_prices(self, symbols):
        return {}


def test_alert_when_a_position_stays_without_its_exchange_stop(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(exchange_stops.time, "monotonic", lambda: clock["t"])
    exchange = RejectingExchange()
    ins = make_instrument(symbol=SYMBOL, category="volumen", stop_loss_pct=0.05, take_profit_pct=0.20)
    config = Config(mode="live", instruments=[ins], risk=RiskConfig(starting_balance=10_000))
    config.engine.exchange_stops = True
    risk = RiskManager(config.risk)
    risk.reset_day(config.risk.starting_balance)
    notifier = MagicMock()
    engine = Engine(config, strategies={SYMBOL: Switch()}, risk=risk, execution=PaperExecutionEngine(config),
                    storage=Storage(":memory:"), exchange=exchange, enforce_daily_loss=False, notifier=notifier)
    now = {"t": pd.Timestamp("2026-10-13 11:20", tz="UTC").to_pydatetime()}
    engine._now = lambda: now["t"]
    engine.process(SYMBOL, _candles(1.00))                        # abre; el exchange rechaza la orden de stop
    assert engine.positions[0].stop_order_id == ""
    alerts = lambda: [c for c in notifier.notify.call_args_list if "sin stop de emergencia" in c.args[0]]

    engine.sync_exchange_stops()
    assert alerts() == []                                         # acaba de fallar: aún no

    clock["t"] += UNPROTECTED_ALERT_SECONDS + 1
    now["t"] += pd.Timedelta(seconds=UNPROTECTED_ALERT_SECONDS + 1)
    engine.sync_exchange_stops()
    assert len(alerts()) == 1
    text = alerts()[0].args[0]
    assert SYMBOL in text and "123002" in text and "15 min" in text

    clock["t"] += 600
    now["t"] += pd.Timedelta(seconds=600)
    engine.sync_exchange_stops()
    assert len(alerts()) == 1                                     # como mucho un aviso por hora

    exchange.reject = False                                       # el exchange vuelve a aceptar órdenes
    clock["t"] += 600
    now["t"] += pd.Timedelta(seconds=600)
    engine.sync_exchange_stops()
    assert engine.positions[0].stop_order_id == "s1"
    clock["t"] += 7200
    now["t"] += pd.Timedelta(seconds=7200)
    engine.sync_exchange_stops()
    assert len(alerts()) == 1                                     # recuperado: no avisa más
    assert engine.stop_guard.unprotected(engine.positions, 0) == []
