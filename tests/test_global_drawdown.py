import pytest
from unittest.mock import MagicMock, patch
import pandas as pd

from tradebot.config import RiskConfig, Config, Instrument
from tradebot.risk import RiskManager
from tradebot.models import Position, Side
from tradebot.engine import Engine


def test_global_drawdown_halts_and_closes():
    # 1. Configurar riesgo y manager
    risk_cfg = RiskConfig(
        starting_balance=1000.0,
        max_daily_loss_pct=0.99,        # Desactivamos el cortafuegos diario
        max_account_drawdown_pct=0.10,  # 10% Drawdown máximo de cuenta
    )
    risk = RiskManager(risk_cfg)
    
    # Simular equity inicial de 1000 y luego una pérdida de 890 (drawdown del 11%)
    risk.register_equity(1000.0)
    assert not risk.halted
    
    risk.register_equity(890.0)
    assert risk.halted
    assert risk.halted_reason == "drawdown_cuenta"


def test_engine_executes_emergency_close():
    # 2. Configurar mock de engine y base de datos
    risk_cfg = RiskConfig(
        starting_balance=1000.0,
        max_daily_loss_pct=0.99,        # Desactivamos el cortafuegos diario
        max_account_drawdown_pct=0.10,  # 10% Drawdown máximo de cuenta
    )
    config = MagicMock(spec=Config)
    config.risk = risk_cfg
    config.effective_db_path = MagicMock(return_value=":memory:")
    
    strategy_mock = MagicMock()
    # Mockear generate_signal para retornar HOLD para evitar nuevas entradas durante el test
    strategy_mock.generate_signal = MagicMock()
    strategy_mock.min_candles = 1
    
    strategies = {"ADA/USDT": strategy_mock}
    risk = RiskManager(risk_cfg)
    risk.set_ath_equity(1000.0)
    risk.reset_day(1000.0)
    execution = MagicMock()
    storage = MagicMock()
    storage.get_state = MagicMock(return_value=None)
    
    engine = Engine(
        config, strategies, risk, execution, storage,
        enforce_daily_loss=True,
    )
    
    # Crear una posición abierta simulada
    inst = Instrument("ADA/USDT", "momentum", "momentum", {}, 0.05, 0.10, 0.15)
    pos = engine.risk.build_position(inst, Side.BUY, 100.0, 0.20, 0.01, "test_open")
    engine.positions.append(pos)
    
    # Sobrescribir equity del motor para forzar caída por debajo del 10%
    engine.equity = MagicMock(return_value=890.0)
    
    # Crear vela mock
    candles = pd.DataFrame(
        {"close": [0.20]},
        index=pd.date_range("2024-01-01", periods=1, tz="UTC")
    )
    
    # Mockear _close_position para verificar que se llama
    engine._close_position = MagicMock(return_value=True)
    
    # Procesar y verificar disparo del disyuntor
    engine.process("ADA/USDT", candles)
    
    # Verificar que el RiskManager está parado
    assert engine.risk.halted
    assert engine.risk.halted_reason == "drawdown_cuenta"
    
    # Verificar que se intentó cerrar la posición de emergencia
    engine._close_position.assert_called_once()
