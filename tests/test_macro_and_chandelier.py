import pytest
import pandas as pd
from unittest.mock import MagicMock
from tradebot.regime import is_btc_macro_bullish
from tradebot.config import Config, Instrument, RiskConfig
from tradebot.models import Position, Side, Signal, SignalType
from tradebot.risk import RiskManager
from tradebot.engine import Engine
from tradebot.storage import Storage

def test_is_btc_macro_bullish():
    exchange = MagicMock()

    # Simular BTC por encima de la EMA50 (alcista)
    prices_bull = [100.0] * 50 + [150.0] * 10
    exchange.fetch_ohlcv.return_value = pd.DataFrame({"close": prices_bull})
    assert is_btc_macro_bullish(exchange) is True

    # Simular BTC por debajo de la EMA50 (bajista)
    prices_bear = [200.0] * 50 + [100.0] * 10
    exchange.fetch_ohlcv.return_value = pd.DataFrame({"close": prices_bear})
    assert is_btc_macro_bullish(exchange) is False

def test_atr_chandelier_trailing_stop():
    inst = Instrument(
        symbol="SOL/USDT", category="breakout", strategy_name="breakout",
        strategy_params={}, stop_loss_pct=0.08, take_profit_pct=0.30,
        position_size_pct=0.20, use_atr_trailing=True, atr_trailing_mult=3.0
    )
    risk_cfg = RiskConfig()
    rm = RiskManager(risk_cfg)

    pos = rm.build_position(inst, Side.BUY, amount=10.0, entry_price=100.0, entry_fee=0.1, reason="test")
    assert pos.use_atr_trailing is True
    assert pos.atr_trailing_mult == 3.0
    initial_sl = pos.stop_loss  # 92.0

    # Precio sube a 110 con ATR = 2.0. Distancia = 3.0 * 2.0 = 6.0.
    # Trail = 110 - 6.0 = 104.0. Stop_loss debe subir a 104.0
    rm.evaluate_exit(pos, current_price=110.0, current_atr=2.0)
    assert pos.peak_price == 110.0
    assert pos.stop_loss == 104.0

    # Precio cae a 105 con ATR = 2.0. El stop_loss NO debe aflojarse (se mantiene en 104.0)
    rm.evaluate_exit(pos, current_price=105.0, current_atr=2.0)
    assert pos.stop_loss == 104.0

    # Precio cae a 103.0 (por debajo de 104.0) -> debe activarse el trailing stop
    decision = rm.evaluate_exit(pos, current_price=103.0, current_atr=2.0)
    assert decision.order is not None
    assert decision.order.reason == "trailing-stop"

def test_macro_btc_filter_blocks_entry(tmp_path):
    db_path = str(tmp_path / "test.db")
    storage = Storage(db_path)

    config = MagicMock(spec=Config)
    config.risk = RiskConfig(starting_balance=1000.0, quote_currency="USDT")
    config.mode = "paper"
    config.effective_db_path.return_value = db_path

    inst = Instrument(
        symbol="SOL/USDT", category="breakout_diario", strategy_name="breakout",
        strategy_params={}, stop_loss_pct=0.08, take_profit_pct=0.30,
        position_size_pct=0.20, macro_btc_filter=True
    )
    config.instrument.return_value = inst

    exchange = MagicMock()
    # Simular BTC bajista (< EMA50)
    prices_bear = [200.0] * 50 + [100.0] * 10
    exchange.fetch_ohlcv.return_value = pd.DataFrame({"close": prices_bear})

    strategy_mock = MagicMock()
    strategy_mock.generate_signal.return_value = Signal(
        type=SignalType.BUY, symbol="SOL/USDT", price=102.0, reason="breakout"
    )

    rm = RiskManager(config.risk)
    execution = MagicMock()

    engine = Engine(config, {"SOL/USDT": strategy_mock}, rm, execution, storage, exchange=exchange)

    candles = pd.DataFrame({
        "open": [100.0]*30, "high": [105.0]*30, "low": [95.0]*30, "close": [102.0]*30, "volume": [1000]*30
    })

    # Ejecutar _check_entry: debe ser bloqueada por el filtro macro BTC
    engine._check_entry("SOL/USDT", candles, 102.0)

    # Verificar que NO se ejecutó ninguna orden de entrada
    execution.execute.assert_not_called()
