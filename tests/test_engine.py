"""Test de integración de un ciclo completo, sin red."""

from conftest import make_config, make_instrument

from tradebot.engine import Engine
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.mean_reversion import MeanReversionStrategy


def _engine(config):
    symbol = config.instruments[0].symbol
    strategy = MeanReversionStrategy(
        rsi_period=14, rsi_oversold=35, bb_period=20, bb_std=2.0
    )
    risk = RiskManager(config.risk)
    risk.reset_day(config.risk.starting_balance)
    execution = PaperExecutionEngine(config)
    storage = Storage(":memory:")
    return Engine(config, strategies={symbol: strategy}, risk=risk,
                  execution=execution, storage=storage, enforce_daily_loss=False)


def test_process_opens_position_on_buy_signal(price_series):
    config = make_config(make_instrument(symbol="BTC/USDT"), starting_balance=10_000)
    engine = _engine(config)

    prices = [100.0] * 25 + [95, 90, 85, 80, 70]
    engine.process("BTC/USDT", price_series(prices))

    assert len(engine.positions) == 1
    assert engine.storage.fill_count() == 1


def test_position_closes_and_records_pnl(price_series):
    config = make_config(make_instrument(symbol="BTC/USDT"), starting_balance=10_000)
    engine = _engine(config)

    # 1) Abre por sobreventa.
    prices = [100.0] * 25 + [95, 90, 85, 80, 70]
    engine.process("BTC/USDT", price_series(prices))
    assert len(engine.positions) == 1
    entry = engine.positions[0].entry_price

    # 2) Precio por encima del take-profit -> cierra y registra ClosedTrade.
    recovery = prices + [entry * 1.10]
    engine.process("BTC/USDT", price_series(recovery))
    assert len(engine.positions) == 0
    assert engine.storage.trade_count() == 1  # un round-trip cerrado

    trades = engine.storage.all_trades()
    assert trades[0]["pnl_abs"] > 0          # fue ganadora
    assert trades[0]["exit_reason"] == "take-profit"
    assert trades[0]["symbol"] == "BTC/USDT"
