"""Stops de emergencia en el exchange: una orden de stop por posición, por debajo del
stop del bot, que protege si el bot se cae. Sin órdenes huérfanas y sin ventas dobles."""

from unittest.mock import MagicMock

import ccxt
import pandas as pd
import pytest
from conftest import make_instrument

from tradebot.config import Config, RiskConfig
from tradebot.engine import Engine
from tradebot.exchange import Exchange
from tradebot.exchange_stops import CLIENT_PREFIX
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.models import Fill, Side, Signal, SignalType
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.base import Strategy

SYMBOL = "ADA/USDT"


class Switch(Strategy):
    def __init__(self):
        self.buy = True

    def generate_signal(self, symbol, candles):
        price = float(candles["close"].iloc[-1])
        return Signal(SignalType.BUY if self.buy else SignalType.HOLD, symbol, price)


class FakeExchange:
    """KuCoin de mentira: guarda órdenes de stop y saldos."""

    def __init__(self):
        self.orders, self.balances, self.fills = {}, {}, {}
        self.n, self.cancelled, self.fail_create, self.list_fails = 0, [], False, False
        self.hidden = set()                         # órdenes que el listado aún no muestra

    def create_stop_sell(self, symbol, amount, trigger_price, client_id):
        if self.fail_create:
            raise ConnectionError("sin red")
        self.n += 1
        order = dict(id=f"s{self.n}", client_id=client_id, symbol=symbol, amount=amount, trigger_price=trigger_price)
        self.orders[order["id"]] = order
        return dict(order)

    def cancel_stop_order(self, order_id, symbol):
        if order_id in self.orders:
            del self.orders[order_id]
            self.cancelled.append(order_id)
            return True
        return False

    def fetch_open_stop_orders(self):
        if self.list_fails:
            raise ConnectionError("sin red")
        return [dict(o) for k, o in self.orders.items() if k not in self.hidden]

    def fetch_balance(self, currency):
        return self.balances.get(currency, 0.0)

    def fetch_balances_total(self):
        return dict(self.balances)

    def fetch_order_fill(self, order_id, symbol):
        return self.fills.get(order_id)

    def fetch_last_prices(self, symbols):
        return {}

    def trigger(self, order_id, price=None, report_fill=True):
        """El exchange ejecuta la orden de stop: desaparece del listado y vende el activo."""
        order = self.orders.pop(order_id)
        self.balances[order["symbol"].split("/")[0]] = 0.0
        if report_fill:
            px = price or order["trigger_price"] * 0.999
            self.fills[order_id] = {"id": order_id, "filled": order["amount"], "average": px, "fee": {"cost": 0.05}}


class Execution(PaperExecutionEngine):
    """Ejecución de papel que mantiene el saldo del activo en el exchange de mentira
    y confirma ejecuciones como el motor live."""

    def __init__(self, config, exchange):
        super().__init__(config)
        self.exchange, self.sells = exchange, 0

    def execute(self, order):
        base = order.symbol.split("/")[0]
        if order.side is Side.SELL:
            if self.exchange.balances.get(base, 0.0) <= 0:
                raise RuntimeError("insufficient balance")
            self.sells += 1
        fill = super().execute(order)
        delta = fill.filled_amount if order.side is Side.BUY else -fill.filled_amount
        self.exchange.balances[base] = max(self.exchange.balances.get(base, 0.0) + delta, 0.0)
        return fill

    def confirm_fill(self, fill):
        result = self.exchange.fetch_order_fill(fill.order_id, fill.order.symbol) if fill.order_id else None
        if result is None:
            return None
        return Fill(order=fill.order, filled_price=float(result["average"]), filled_amount=float(result["filled"]),
                    fee=float(result["fee"]["cost"]), order_id=fill.order_id, confirmed=True)


def _candles(price: float) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=1, freq="4h", tz="UTC")
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 1.0}, index=idx)


def _engine(exchange=None, storage=None, enabled=True, mode="live", **ins_kw):
    ins = make_instrument(symbol=SYMBOL, category="volumen", stop_loss_pct=0.05, take_profit_pct=0.20, **ins_kw)
    config = Config(mode=mode, instruments=[ins], risk=RiskConfig(starting_balance=10_000))
    config.engine.fee_pct, config.engine.slippage_pct = 0.001, 0.0
    config.engine.exchange_stops = enabled
    config.engine.exchange_stop_buffer_pct, config.engine.exchange_stop_min_move_pct = 0.02, 0.005
    exchange = exchange if exchange is not None else FakeExchange()
    risk = RiskManager(config.risk)
    risk.reset_day(config.risk.starting_balance)
    return Engine(config, strategies={SYMBOL: Switch()}, risk=risk, execution=Execution(config, exchange),
                  storage=storage or Storage(":memory:"), exchange=exchange, enforce_daily_loss=False)


def _open(engine, price=1.00):
    engine.process(SYMBOL, _candles(price))
    engine.strategies[SYMBOL].buy = False
    return engine.positions[0]


# --- colocación ---------------------------------------------------------------------------------

def test_disabled_by_default_never_touches_the_exchange():
    exchange = MagicMock()
    exchange.fetch_last_prices.return_value = {}
    engine = _engine(exchange=exchange, enabled=False)
    engine.execution.exchange = FakeExchange()
    engine.process(SYMBOL, _candles(1.00))
    engine.sync_exchange_stops()

    assert engine.stop_guard.enabled is False
    exchange.create_stop_sell.assert_not_called()
    exchange.fetch_open_stop_orders.assert_not_called()
    assert engine.release_exchange_stops() == 0            # nunca se usaron: tampoco limpia
    exchange.fetch_open_stop_orders.assert_not_called()


def test_only_in_live_mode():
    assert _engine(mode="paper").stop_guard.enabled is False


def test_opening_a_position_places_a_stop_below_the_bots_stop():
    engine = _engine()
    pos = _open(engine)

    (order,) = engine.exchange.orders.values()
    assert pos.stop_loss == pytest.approx(0.95)
    assert order["trigger_price"] == pytest.approx(0.95 * 0.98)          # 2% por debajo del stop del bot
    assert order["amount"] == pytest.approx(pos.amount)
    assert order["client_id"].startswith(CLIENT_PREFIX)
    assert pos.stop_order_id == order["id"]
    saved = engine.storage.load_open_positions()[0]                      # sobrevive a un reinicio
    assert (saved.stop_order_id, saved.stop_order_price) == (order["id"], pytest.approx(0.931))


def test_order_amount_never_exceeds_the_real_balance():
    engine = _engine(trailing_stop_pct=0.05)
    pos = _open(engine)
    engine.exchange.balances["ADA"] = pos.amount * 0.999                # la comisión de compra se cobró en ADA

    engine.process(SYMBOL, _candles(1.10))                               # el trailing repone la orden

    (order,) = engine.exchange.orders.values()
    assert order["amount"] == pytest.approx(pos.amount * 0.999)          # si pidiera más, no se ejecutaría
    engine.process(SYMBOL, _candles(1.10))
    assert len(engine.exchange.orders) == 1 and engine.exchange.n == 2   # y esa diferencia no la hace reponer otra vez


def test_a_failure_placing_the_stop_does_not_block_the_position():
    exchange = FakeExchange()
    exchange.fail_create = True
    engine = _engine(exchange=exchange)
    pos = _open(engine)

    assert pos.stop_order_id == "" and exchange.orders == {}
    exchange.fail_create = False
    engine.sync_exchange_stops()                                         # falló hace poco: aún no insiste
    assert exchange.orders == {}
    engine.stop_guard._retry_after.clear()                               # pasados unos minutos, lo repone
    engine.sync_exchange_stops()
    assert pos.stop_order_id in exchange.orders


# --- seguimiento del stop del bot ---------------------------------------------------------------

def test_trailing_replaces_the_order_only_when_the_stop_moves_enough():
    engine = _engine(trailing_stop_pct=0.05)
    pos = _open(engine)
    first = pos.stop_order_id

    engine.process(SYMBOL, _candles(1.003))                              # el stop sube un 0,3%: no merece reponer
    assert pos.stop_order_id == first and len(engine.exchange.orders) == 1

    engine.process(SYMBOL, _candles(1.10))                               # el stop sube a 1,045
    (order,) = engine.exchange.orders.values()
    assert pos.stop_order_id == order["id"] != first
    assert order["trigger_price"] == pytest.approx(1.10 * 0.95 * 0.98)
    assert engine.exchange.cancelled == [first]                          # la anterior se retira después de crear la nueva


def test_partial_take_profit_resizes_the_order():
    engine = _engine(trailing_stop_pct=0.0)
    ins = engine.config.instruments[0]
    ins.partial_take_profit_pct, ins.partial_take_profit_ratio = 0.05, 0.5
    pos = _open(engine)
    amount = pos.amount

    engine.process(SYMBOL, _candles(1.06))                               # toma parcial: vende la mitad, stop a la entrada

    (order,) = engine.exchange.orders.values()
    assert order["amount"] == pytest.approx(amount / 2)
    assert order["trigger_price"] == pytest.approx(pos.entry_price * 0.98)
    assert len(engine.positions) == 1


# --- ventas del bot -----------------------------------------------------------------------------

@pytest.mark.parametrize("price, reason", [(1.25, "take-profit"), (0.94, "stop-loss")])
def test_bot_exit_cancels_the_order_first(price, reason):
    engine = _engine()
    pos = _open(engine)
    order_id = pos.stop_order_id

    engine.process(SYMBOL, _candles(price))

    assert engine.positions == []
    assert engine.exchange.orders == {} and engine.exchange.cancelled == [order_id]
    assert engine.execution.sells == 1
    (trade,) = engine.storage.all_trades()
    assert trade["exit_reason"] == reason and trade["exit_price"] == pytest.approx(price)


def test_failed_bot_sale_restores_the_order():
    engine = _engine()
    pos = _open(engine)

    def boom(order):
        raise ConnectionError("sin red")

    real_execute = engine.execution.execute
    engine.execution.execute = boom
    engine.process(SYMBOL, _candles(1.25))                               # no consigue vender

    assert len(engine.positions) == 1
    assert pos.stop_order_id in engine.exchange.orders                   # vuelve a estar protegida
    engine.execution.execute = real_execute


# --- ventas del exchange ------------------------------------------------------------------------

def test_exchange_sold_before_the_bot_reacted_no_double_sale():
    engine = _engine()
    pos = _open(engine)
    engine.exchange.trigger(pos.stop_order_id, price=0.925)              # una caída brusca dispara la orden

    engine.process(SYMBOL, _candles(0.90))                               # el bot ve el precio bajo su stop

    assert engine.positions == [] and engine.execution.sells == 0        # no intenta vender otra vez
    (trade,) = engine.storage.all_trades()
    assert trade["exit_reason"] == "stop-loss"
    assert trade["exit_price"] == pytest.approx(0.925)                   # precio real de la orden
    assert trade["stop_price"] == pytest.approx(0.95)                    # nivel del stop del bot
    assert engine.storage.load_open_positions() == []


def test_cycle_sync_detects_a_sale_the_bot_never_saw():
    engine = _engine()
    pos = _open(engine)
    order_id = pos.stop_order_id
    engine.stop_guard._created.clear()                                   # ya no es una orden recién creada
    engine.exchange.trigger(order_id, report_fill=False)                 # mecha: se dispara y el precio vuelve

    engine.process(SYMBOL, _candles(1.00))                               # el bot no ve nada raro
    assert len(engine.positions) == 1
    engine.sync_exchange_stops()

    assert engine.positions == []
    (trade,) = engine.storage.all_trades()
    assert trade["exit_price"] == pytest.approx(0.931)                   # estimado: el precio de disparo
    assert len(engine._unconfirmed) == 1                                 # y pendiente de confirmar

    engine.exchange.fills[order_id] = {"id": order_id, "filled": pos.amount, "average": 0.928, "fee": {"cost": 0.09}}
    assert engine.reconcile_fills() == 1
    assert engine.storage.all_trades()[0]["exit_price"] == pytest.approx(0.928)


def test_recent_order_missing_from_a_lagging_listing_is_left_alone():
    engine = _engine()
    pos = _open(engine)
    engine.exchange.hidden.add(pos.stop_order_id)                        # el listado aún no la muestra

    engine.sync_exchange_stops()

    assert len(engine.positions) == 1 and len(engine.exchange.orders) == 1


def test_vanished_order_is_replaced_when_the_asset_is_still_there():
    engine = _engine()
    pos = _open(engine)
    old = pos.stop_order_id
    engine.stop_guard._created.clear()
    del engine.exchange.orders[old]                                      # cancelada a mano en KuCoin

    engine.sync_exchange_stops()

    assert len(engine.positions) == 1
    assert pos.stop_order_id != old and pos.stop_order_id in engine.exchange.orders


def test_listing_failure_changes_nothing():
    engine = _engine()
    pos = _open(engine)
    engine.stop_guard._created.clear()
    engine.exchange.list_fails = True

    engine.sync_exchange_stops()

    assert len(engine.positions) == 1 and pos.stop_order_id in engine.exchange.orders


def test_unknown_state_waits_instead_of_selling_blind():
    engine = _engine()
    pos = _open(engine)
    del engine.exchange.orders[pos.stop_order_id]                        # la orden ya no está…

    def no_balance(currency):
        raise ConnectionError("sin red")

    engine.exchange.fetch_balance = no_balance                           # …y no se puede leer el saldo
    engine.exchange.fetch_balances_total = lambda: no_balance(None)
    engine.process(SYMBOL, _candles(0.90))

    assert len(engine.positions) == 1 and engine.execution.sells == 0    # ni vende ni la da por cerrada
    assert engine.storage.all_trades() == []


def test_cancel_error_does_not_stop_the_bot_from_selling():
    engine = _engine()
    pos = _open(engine)
    order_id = pos.stop_order_id

    def boom(oid, symbol):
        raise ConnectionError("sin red")

    real_cancel = engine.exchange.cancel_stop_order
    engine.exchange.cancel_stop_order = boom
    engine.process(SYMBOL, _candles(0.94))                               # stop del bot: vender es lo prioritario

    assert engine.positions == [] and engine.execution.sells == 1
    assert order_id in engine.exchange.orders                            # queda viva…
    engine.exchange.cancel_stop_order = real_cancel
    engine.sync_exchange_stops()
    assert engine.exchange.orders == {}                                  # …y se cancela como huérfana


def test_cancel_error_with_the_asset_already_sold_records_the_exchange_sale():
    engine = _engine()
    pos = _open(engine)
    engine.exchange.trigger(pos.stop_order_id, price=0.925)

    def boom(oid, symbol):
        raise ConnectionError("sin red")

    engine.exchange.cancel_stop_order = boom
    engine.process(SYMBOL, _candles(0.90))

    assert engine.positions == [] and engine.execution.sells == 0
    assert engine.storage.all_trades()[0]["exit_price"] == pytest.approx(0.925)


def test_orphans_that_cannot_be_cancelled_raise_an_alert():
    messages = []

    class Recorder:
        def notify(self, text):
            messages.append(text)

        def __getattr__(self, name):
            return lambda *a, **k: None

    engine = _engine()
    engine.notifier = Recorder()
    _open(engine)
    exchange = engine.exchange
    exchange.orders["huerfana"] = dict(id="huerfana", client_id=CLIENT_PREFIX + "vieja", symbol=SYMBOL, amount=1.0, trigger_price=0.5)
    real_cancel = exchange.cancel_stop_order
    exchange.cancel_stop_order = lambda oid, symbol: False if oid == "huerfana" else real_cancel(oid, symbol)

    engine.sync_exchange_stops()
    engine.sync_exchange_stops()                                         # no repite el aviso en cada ciclo

    alerts = [m for m in messages if "sin posición" in m]
    assert len(alerts) == 1 and "huerfana" in alerts[0]


def test_status_shows_the_exchange_stop():
    from tradebot import status
    engine = _engine()
    _open(engine)
    engine.exchange.fetch_last_price = lambda s: 1.0

    st = status.build_status(engine, engine.config)

    assert st["open_positions"][0]["exchange_stop"] == pytest.approx(0.931)


# --- huérfanas ----------------------------------------------------------------------------------

def test_orphans_with_our_prefix_are_cancelled_and_foreign_orders_left_alone():
    engine = _engine()
    pos = _open(engine)
    exchange = engine.exchange
    exchange.orders["huerfana"] = dict(id="huerfana", client_id=CLIENT_PREFIX + "vieja", symbol=SYMBOL, amount=1.0, trigger_price=0.5)
    exchange.orders["ajena"] = dict(id="ajena", client_id="mi-orden-manual", symbol="BTC/USDT", amount=0.1, trigger_price=50_000.0)

    engine.sync_exchange_stops()

    assert set(exchange.orders) == {pos.stop_order_id, "ajena"}


# --- reinicios y desactivación ------------------------------------------------------------------

def test_sale_while_the_bot_was_down_is_recorded_at_restart(tmp_path):
    db = tmp_path / "bot.db"
    exchange = FakeExchange()
    first = _engine(exchange=exchange, storage=Storage(db))
    pos = _open(first)
    order_id = pos.stop_order_id
    first.storage.close()
    exchange.trigger(order_id, price=0.92)                               # se dispara con el bot parado

    second = _engine(exchange=exchange, storage=Storage(db))
    assert second.load_positions() == 0

    (trade,) = second.storage.all_trades()                               # es un cierre, no un descarte
    assert trade["exit_reason"] == "stop-loss" and trade["exit_price"] == pytest.approx(0.92)
    second.storage.close()


def test_restart_keeps_the_existing_order(tmp_path):
    db = tmp_path / "bot.db"
    exchange = FakeExchange()
    first = _engine(exchange=exchange, storage=Storage(db))
    order_id = _open(first).stop_order_id
    first.storage.close()

    second = _engine(exchange=exchange, storage=Storage(db))
    second.load_positions()
    second.sync_exchange_stops()

    assert second.positions[0].stop_order_id == order_id
    assert list(exchange.orders) == [order_id] and exchange.cancelled == []
    second.storage.close()


def test_turning_the_option_off_removes_the_bots_orders(tmp_path):
    db = tmp_path / "bot.db"
    exchange = FakeExchange()
    first = _engine(exchange=exchange, storage=Storage(db))
    _open(first)
    exchange.orders["ajena"] = dict(id="ajena", client_id="manual", symbol="BTC/USDT", amount=0.1, trigger_price=1.0)
    first.storage.close()

    second = _engine(exchange=exchange, storage=Storage(db), enabled=False)
    second.load_positions()
    assert second.release_exchange_stops() == 1

    assert list(exchange.orders) == ["ajena"]
    assert second.positions[0].stop_order_id == ""
    assert second.storage.load_open_positions()[0].stop_order_id == ""
    second.storage.close()


# --- llamadas a ccxt ----------------------------------------------------------------------------

def _wrapper():
    ex = Exchange.__new__(Exchange)
    ex._client = MagicMock()
    ex._client.amount_to_precision.side_effect = lambda s, a: f"{a:.4f}"
    ex._client.price_to_precision.side_effect = lambda s, p: f"{p:.5f}"
    ex._normalize_symbol = lambda s: s
    return ex


def test_create_stop_sell_sends_a_stop_loss_market_order():
    ex = _wrapper()
    ex._client.create_order.return_value = {"id": "abc", "info": {}}

    order = ex.create_stop_sell(SYMBOL, 123.456789, 0.2512349, "tbstop-1")

    ex._client.create_order.assert_called_once_with(SYMBOL, "market", "sell", 123.4568, None,
                                                    {"stopLossPrice": 0.25123, "clientOid": "tbstop-1"})
    assert order == {"id": "abc", "client_id": "tbstop-1", "symbol": SYMBOL, "amount": 123.4568,
                     "trigger_price": 0.25123, "status": None}


def test_create_stop_sell_rejects_zero_amounts():
    with pytest.raises(ValueError):
        _wrapper().create_stop_sell(SYMBOL, 0.00001, 0.25, "tbstop-1")


def test_cancel_stop_order_uses_the_trigger_endpoint_and_reports_missing_orders():
    ex = _wrapper()
    assert ex.cancel_stop_order("abc", SYMBOL) is True
    ex._client.cancel_order.assert_called_once_with("abc", SYMBOL, {"trigger": True})

    ex._client.cancel_order.side_effect = ccxt.OrderNotFound("order not exist")
    assert ex.cancel_stop_order("abc", SYMBOL) is False

    for unknown in (ccxt.NetworkError("timeout"), ccxt.BadRequest("parámetro incorrecto")):
        ex._client.cancel_order.side_effect = unknown                        # no saber no es "ya no existe"
        with pytest.raises(type(unknown)):
            ex.cancel_stop_order("abc", SYMBOL)


def test_fetch_open_stop_orders_maps_ccxt_fields():
    ex = _wrapper()
    ex._client.fetch_open_orders.return_value = [
        {"id": "abc", "clientOrderId": "tbstop-1", "symbol": SYMBOL, "amount": 10.0, "triggerPrice": 0.25, "status": "open", "info": {}},
        {"id": None, "info": {"id": "xyz", "clientOid": "manual", "stopPrice": "1.5"}, "symbol": "BTC/USDT", "amount": 1.0},
    ]

    orders = ex.fetch_open_stop_orders()

    ex._client.fetch_open_orders.assert_called_once_with(None, None, None, {"trigger": True})
    assert orders[0] == {"id": "abc", "client_id": "tbstop-1", "symbol": SYMBOL, "amount": 10.0, "trigger_price": 0.25, "status": "open"}
    assert (orders[1]["id"], orders[1]["client_id"], orders[1]["trigger_price"]) == ("xyz", "manual", "1.5")
