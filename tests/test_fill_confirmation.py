"""Ejecuciones que el exchange no confirma a tiempo (se registran con datos estimados
y se corrigen después) y equity correcto nada más readoptar posiciones."""

import pandas as pd
import pytest
from conftest import make_instrument

from tradebot import status
from tradebot.config import Config, RiskConfig
from tradebot.engine import Engine
from tradebot.execution.live import LiveExecutionEngine
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.models import Fill, Order, Side, Signal, SignalType
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


class LaggyExecution(PaperExecutionEngine):
    """Como KuCoin con retraso: devuelve datos estimados (precio de referencia, cantidad
    pedida, comisión 0) y solo confirma los reales cuando `ready` es True."""

    def __init__(self, config, lag=("buy", "sell")):
        super().__init__(config)
        self.lag, self.ready, self.real, self.asked = set(lag), False, {}, 0

    def execute(self, order):
        fill = super().execute(order)
        if order.side.value not in self.lag:
            return fill
        order_id = f"ord-{len(self.real) + 1}"
        worse = 1.002 if order.side is Side.BUY else 0.990        # el precio real es peor que el estimado
        self.real[order_id] = Fill(order=order, filled_price=order.price * worse,
                                   filled_amount=order.amount * 0.998, fee=0.5,
                                   order_id=order_id, confirmed=True)
        return Fill(order=order, filled_price=order.price, filled_amount=order.amount, fee=0.0,
                    order_id=order_id, confirmed=False)

    def confirm_fill(self, fill):
        self.asked += 1
        return self.real[fill.order_id] if self.ready else None


class PriceExchange:
    def __init__(self, prices, fail=False):
        self.prices, self.fail = prices, fail

    def fetch_last_prices(self, symbols):
        if self.fail:
            raise ConnectionError("sin red")
        return {s: self.prices[s] for s in symbols if s in self.prices}

    def fetch_last_price(self, symbol):
        return self.prices[symbol]


def _candles(price: float) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=1, freq="4h", tz="UTC")
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 1.0}, index=idx)


def _config():
    ins = make_instrument(symbol=SYMBOL, category="volumen", stop_loss_pct=0.05, take_profit_pct=0.20)
    config = Config(instruments=[ins], risk=RiskConfig(starting_balance=10_000))
    config.engine.fee_pct = 0.001
    config.engine.slippage_pct = 0.0
    return config


def _engine(execution=None, storage=None, exchange=None, lag=("buy", "sell")):
    config = _config()
    risk = RiskManager(config.risk)
    risk.reset_day(config.risk.starting_balance)
    execution = execution or LaggyExecution(config, lag=lag)
    return Engine(config, strategies={SYMBOL: Switch()}, risk=risk, execution=execution,
                  storage=storage or Storage(":memory:"), exchange=exchange, enforce_daily_loss=False)


# --- Compras -----------------------------------------------------------------------------------

def test_unconfirmed_buy_is_corrected_when_the_exchange_confirms():
    engine = _engine(lag=("buy",))
    engine.process(SYMBOL, _candles(1.00))
    pos = engine.positions[0]
    estimated_amount, stop, take = pos.amount, pos.stop_loss, pos.take_profit
    assert pos.entry_price == 1.00 and pos.entry_fee == 0.0          # datos estimados

    assert engine.reconcile_fills() == 0                              # aún no consta: sigue pendiente
    assert pos.entry_price == 1.00

    engine.execution.ready = True
    assert engine.reconcile_fills() == 1
    assert pos.entry_price == pytest.approx(1.002)
    assert pos.amount == pytest.approx(estimated_amount * 0.998)
    assert pos.entry_fee == pytest.approx(0.5)
    assert (pos.stop_loss, pos.take_profit) == (stop, take)           # los niveles no se mueven

    saved = engine.storage.load_open_positions()[0]                   # y queda persistido
    assert saved.entry_price == pytest.approx(1.002)
    assert saved.amount == pytest.approx(estimated_amount * 0.998)
    assert saved.entry_fee == pytest.approx(0.5)

    asked = engine.execution.asked
    assert engine.reconcile_fills() == 0                              # nada pendiente: no vuelve a preguntar
    assert engine.execution.asked == asked


def test_buy_confirmed_after_the_position_closed_changes_nothing():
    engine = _engine(lag=("buy",))
    engine.process(SYMBOL, _candles(1.00))
    engine.strategies[SYMBOL].buy = False
    engine.process(SYMBOL, _candles(0.92))                            # salta el stop antes de confirmar
    before = dict(engine.storage.all_trades()[0])

    engine.execution.ready = True
    assert engine.reconcile_fills() == 1
    assert dict(engine.storage.all_trades()[0]) == before
    assert engine.positions == []


# --- Ventas ------------------------------------------------------------------------------------

def test_unconfirmed_stop_sale_is_corrected_in_the_stored_trade():
    engine = _engine(lag=("sell",))
    engine.process(SYMBOL, _candles(1.00))
    pos = engine.positions[0]
    amount, entry_fee, stop = pos.amount, pos.entry_fee, pos.stop_loss
    engine.strategies[SYMBOL].buy = False
    engine.process(SYMBOL, _candles(0.92))

    row = engine.storage.all_trades()[0]
    assert row["exit_price"] == pytest.approx(0.92)                   # estimado: el precio sondeado
    assert row["fee_total"] == pytest.approx(entry_fee)               # sin la comisión de venta

    engine.execution.ready = True
    assert engine.reconcile_fills() == 1
    real_exit = 0.92 * 0.990
    row = engine.storage.all_trades()[0]
    assert row["exit_price"] == pytest.approx(real_exit)
    assert row["fee_total"] == pytest.approx(entry_fee + 0.5)
    assert row["pnl_abs"] == pytest.approx((real_exit - 1.00) * amount - entry_fee - 0.5)
    assert row["pnl_pct"] == pytest.approx(row["pnl_abs"] / (1.00 * amount) * 100)
    assert engine.storage.trade_count() == 1                          # corrige la fila, no añade otra

    # El deslizamiento del stop se mide con el precio real, no con el estimado.
    assert engine.storage.stop_slippage()["avg_pct"] == pytest.approx((real_exit / stop - 1) * 100)
    assert engine.closed_trades[0].exit_price == pytest.approx(real_exit)


def test_gives_up_after_the_maximum_attempts():
    engine = _engine(lag=("sell",))
    engine.MAX_FILL_CONFIRM_ATTEMPTS = 3
    engine.process(SYMBOL, _candles(1.00))
    engine.strategies[SYMBOL].buy = False
    engine.process(SYMBOL, _candles(0.92))

    for _ in range(5):
        assert engine.reconcile_fills() == 0
    assert engine.execution.asked == 3                                # deja de insistir
    assert engine.storage.all_trades()[0]["exit_price"] == pytest.approx(0.92)


def test_a_failing_confirmation_does_not_break_the_cycle():
    engine = _engine(lag=("sell",))
    engine.process(SYMBOL, _candles(1.00))
    engine.strategies[SYMBOL].buy = False
    engine.process(SYMBOL, _candles(0.92))

    def boom(fill):
        raise ConnectionError("sin red")

    engine.execution.confirm_fill = boom
    assert engine.reconcile_fills() == 0
    assert len(engine._unconfirmed) == 1                              # se reintenta en el próximo ciclo


def test_confirmed_fills_are_not_tracked():
    engine = _engine(execution=PaperExecutionEngine(_config()))
    engine.process(SYMBOL, _candles(1.00))
    engine.strategies[SYMBOL].buy = False
    engine.process(SYMBOL, _candles(0.92))

    assert engine._unconfirmed == []
    assert engine.reconcile_fills() == 0


# --- Motor live: detectar y confirmar ----------------------------------------------------------

class OrderExchange:
    def __init__(self, order=None):
        self.order, self.calls = order, []

    def fetch_order_fill(self, order_id, symbol):
        self.calls.append((order_id, symbol))
        return self.order


def _live(exchange=None):
    return LiveExecutionEngine(_config(), exchange or OrderExchange())


def test_live_fill_without_execution_data_is_marked_unconfirmed():
    order = Order(SYMBOL, Side.SELL, 1283.482, 0.2529)
    fill = _live()._to_fill(order, {"id": "abc123"})                  # KuCoin solo devolvió el id

    assert fill.confirmed is False and fill.order_id == "abc123"
    assert (fill.filled_price, fill.filled_amount, fill.fee) == (0.2529, 1283.482, 0.0)


def test_live_fill_with_execution_data_is_confirmed():
    order = Order(SYMBOL, Side.SELL, 1283.482, 0.2529)
    result = {"id": "abc123", "filled": 1283.48, "average": 0.2518, "fee": {"cost": 0.3232, "currency": "USDT"}}
    fill = _live()._to_fill(order, result)

    assert fill.confirmed is True
    assert (fill.filled_price, fill.filled_amount, fill.fee) == (0.2518, 1283.48, 0.3232)


def test_live_confirm_fill_returns_the_real_execution():
    order = Order(SYMBOL, Side.SELL, 1283.482, 0.2529)
    exchange = OrderExchange()
    live = _live(exchange)
    estimated = live._to_fill(order, {"id": "abc123"})

    assert live.confirm_fill(estimated) is None                       # el exchange aún no la refleja
    exchange.order = {"id": "abc123", "filled": 1283.48, "average": 0.2518, "fee": {"cost": 0.3232}}
    real = live.confirm_fill(estimated)

    assert exchange.calls == [("abc123", SYMBOL), ("abc123", SYMBOL)]
    assert real.confirmed is True and real.order_id == "abc123"
    assert (real.filled_price, real.filled_amount, real.fee) == (0.2518, 1283.48, 0.3232)
    assert live.confirm_fill(real) is None                            # una ya confirmada no se consulta


# --- Equity tras readoptar posiciones ----------------------------------------------------------

def _restart(tmp_path, exchange):
    """Abre una posición a 1.00, 'reinicia' el bot y devuelve el motor nuevo."""
    db = tmp_path / "bot.db"
    first = _engine(execution=PaperExecutionEngine(_config()), storage=Storage(db))
    first.process(SYMBOL, _candles(1.00))
    amount, cash = first.positions[0].amount, first.execution.get_balance()
    first.storage.close()

    second = _engine(execution=PaperExecutionEngine(_config()), storage=Storage(db), exchange=exchange)
    assert second.load_positions() == 1
    return second, amount, cash


def test_equity_after_restart_uses_market_prices(tmp_path):
    engine, amount, cash = _restart(tmp_path, PriceExchange({SYMBOL: 0.90}))

    assert engine.last_prices[SYMBOL] == 0.90
    assert engine.equity() == pytest.approx(cash + 0.90 * amount)     # no a 1.00, su entrada


def test_restart_survives_a_price_query_failure(tmp_path):
    engine, amount, cash = _restart(tmp_path, PriceExchange({}, fail=True))

    assert SYMBOL not in engine.last_prices
    assert engine.equity() == pytest.approx(cash + 1.00 * amount)     # sin precio: valora a la entrada


def test_status_equity_matches_the_prices_it_shows(tmp_path):
    engine, amount, cash = _restart(tmp_path, PriceExchange({}, fail=True))
    engine.exchange.fail = False
    engine.exchange.prices = {SYMBOL: 0.90}                           # el status sí consigue el precio

    st = status.build_status(engine, engine.config)

    assert st["open_positions"][0]["current_price"] == 0.90
    assert st["equity"] == pytest.approx(round(cash + 0.90 * amount, 2))
