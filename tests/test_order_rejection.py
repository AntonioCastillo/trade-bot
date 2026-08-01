"""El motor debe sobrevivir a órdenes rechazadas por el exchange (tamaño mínimo,
precisión, etc.) sin romperse: omite la entrada, o mantiene la posición abierta
si falla el cierre (para reintentar)."""

from conftest import make_config, make_instrument

from tradebot.engine import Engine
from tradebot.execution.base import OrderRejected
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.mean_reversion import MeanReversionStrategy


class _RejectAll(PaperExecutionEngine):
    def execute(self, order):
        raise OrderRejected("simulado: por debajo del mínimo")


class _RejectSells(PaperExecutionEngine):
    def execute(self, order):
        from tradebot.models import Side
        if order.side is Side.SELL:
            raise OrderRejected("simulado: venta rechazada")
        return super().execute(order)


def _engine(config, execution):
    symbol = config.instruments[0].symbol
    strategy = MeanReversionStrategy(rsi_period=14, rsi_oversold=35, bb_period=20, bb_std=2.0)
    risk = RiskManager(config.risk)
    risk.reset_day(config.risk.starting_balance)
    return Engine(config, strategies={symbol: strategy}, risk=risk,
                  execution=execution, storage=Storage(":memory:"),
                  enforce_daily_loss=False)


def test_rejected_entry_is_skipped_without_crashing(price_series):
    config = make_config(make_instrument(symbol="BTC/USDT"))
    engine = _engine(config, _RejectAll(config))
    prices = [100.0] * 25 + [95, 90, 85, 80, 70]
    engine.process("BTC/USDT", price_series(prices))  # no debe lanzar
    assert engine.positions == []
    assert engine.storage.fill_count() == 0


def test_failed_close_keeps_position_for_retry(price_series):
    config = make_config(make_instrument(symbol="BTC/USDT"))
    engine = _engine(config, _RejectSells(config))

    # Abre por sobreventa (la compra sí pasa).
    prices = [100.0] * 25 + [95, 90, 85, 80, 70]
    engine.process("BTC/USDT", price_series(prices))
    assert len(engine.positions) == 1
    entry = engine.positions[0].entry_price

    # Precio dispara take-profit, pero la venta se rechaza -> se mantiene abierta.
    engine.process("BTC/USDT", price_series(prices + [entry * 1.10]))
    assert len(engine.positions) == 1
    assert engine.storage.trade_count() == 0
