import numpy as np
import pandas as pd
import pytest

from tradebot.config import Config, Instrument, HedgingConfig
from tradebot.models import SignalType, Side, Order, Position
from tradebot.strategy.breakout import BreakoutStrategy
from tradebot.strategy.momentum import MomentumStrategy
from tradebot.strategy.capitulation import CapitulationStrategy
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.engine import Engine
from tradebot.risk import RiskManager
from tradebot.storage import Storage


def _df(prices, volumes=None):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="1h", tz="UTC")
    close = pd.Series(prices, index=idx)
    vol = volumes if volumes is not None else [100.0] * len(prices)
    return pd.DataFrame(
        {
            "open": close.shift(1).fillna(close),
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": pd.Series(vol, index=idx),
        }
    )


def test_breakout_short():
    prices = [1.0] * 30 + [0.95, 0.90, 0.82, 0.75, 0.65]
    strategy = BreakoutStrategy(lookback=20, bidirectional=True)
    sig = strategy.generate_signal("BTC/USDT", _df(prices))
    assert sig.type is SignalType.SELL
    assert "ruptura mínimo" in sig.reason


def test_momentum_short():
    # Precios cayendo fuerte para trend_ok_short y breakout_ok_short
    prices = [1.0] * 40 + [0.95, 0.90, 0.85, 0.80, 0.70]
    volumes = [100.0] * 44 + [300.0]
    strategy = MomentumStrategy(
        fast_ema=10, slow_ema=30, breakout_lookback=20,
        atr_period=14, breakout_atr_mult=0.5, min_trend_strength=0.0,
        volume_mult=1.0, bidirectional=True
    )
    sig = strategy.generate_signal("BTC/USDT", _df(prices, volumes))
    assert sig.type is SignalType.SELL
    assert "breakout_bajo" in sig.reason


def test_capitulation_buy():
    # Caída abrupta: de 1.0 a 0.90 en una vela (10% drop), volumen alto
    prices = [1.0] * 30 + [0.90]
    volumes = [100.0] * 30 + [500.0]
    strategy = CapitulationStrategy(
        rsi_period=14, rsi_oversold=30.0, lookback=20, drop_pct=0.05, volume_mult=2.0
    )
    sig = strategy.generate_signal("BTC/USDT", _df(prices, volumes))
    assert sig.type is SignalType.BUY
    assert "capitulación" in sig.reason


def test_paper_execution_futures_fee():
    cfg = Config()
    cfg.exchange = "kucoinfutures"
    engine = PaperExecutionEngine(cfg)
    assert engine.fee_pct == 0.0004


class DummyExecution:
    def __init__(self):
        self.balance = 1000.0
        self.orders = []

    def execute(self, order):
        self.orders.append(order)
        from tradebot.models import Fill
        return Fill(order, order.price, order.amount, 0.0)

    def get_balance(self):
        return self.balance


def test_hedging_logic():
    cfg = Config()
    cfg.hedging = HedgingConfig(enabled=True, symbol="BTC/USDT", ratio=0.5, min_positions=1)
    
    # Crear instrumentos
    cfg.instruments = [
        Instrument(
            symbol="ETH/USDT", category="majors", strategy_name="trend",
            strategy_params={}, stop_loss_pct=0.05, take_profit_pct=0.10,
            position_size_pct=0.10
        ),
        Instrument(
            symbol="BTC/USDT", category="majors", strategy_name="trend",
            strategy_params={}, stop_loss_pct=0.05, take_profit_pct=0.10,
            position_size_pct=0.10
        )
    ]
    
    risk = RiskManager(cfg.risk)
    execution = DummyExecution()
    storage = Storage(":memory:")
    
    engine = Engine(cfg, {}, risk, execution, storage)
    engine.last_prices = {"ETH/USDT": 3000.0, "BTC/USDT": 60000.0}
    
    # Añadir una posición larga de altcoin (ETH)
    pos = Position(
        symbol="ETH/USDT", side=Side.BUY, amount=0.1, entry_price=3000.0,
        stop_loss=2850.0, take_profit=3300.0, category="majors", strategy_name="trend"
    )
    engine.positions.append(pos)
    
    # Ejecutar rebalanceo de cobertura
    engine._rebalance_hedging()
    
    # Debe haber abierto una posición de cobertura corta en BTC
    # Altcoin long exposure = 0.1 * 3000 = 300 USDT
    # Target hedge = 300 * 0.5 = 150 USDT
    # BTC price = 60000.0 -> BTC contracts = 150 / 60000 = 0.0025 BTC
    assert len(execution.orders) == 1
    order = execution.orders[0]
    assert order.symbol == "BTC/USDT"
    assert order.side is Side.SELL
    assert pytest.approx(order.amount) == 0.0025
    
    # Ahora la posición corta está en engine.positions
    assert len(engine.positions) == 2
    hedge_pos = [p for p in engine.positions if p.symbol == "BTC/USDT"][0]
    assert hedge_pos.side is Side.SELL
    assert pytest.approx(hedge_pos.amount) == 0.0025
    
    # Si cerramos la posición larga de ETH, el rebalanceo debe cerrar la cobertura
    engine.positions = [hedge_pos]
    execution.orders.clear()
    
    engine._rebalance_hedging()
    
    # Debe haber cerrado el corto de cobertura
    assert len(execution.orders) == 1
    close_order = execution.orders[0]
    assert close_order.symbol == "BTC/USDT"
    assert close_order.side is Side.BUY
