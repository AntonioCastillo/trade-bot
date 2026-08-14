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


def test_anchor_on_start_reanchors_stale_peak():
    # ATH persistido de un capital anterior (600) por encima del equity de
    # arranque (483.90) que ES la base de capital: 19.4% de drawdown importado en
    # reposo, pero no hay pérdida de principal -> re-ancla al equity actual.
    risk_cfg = RiskConfig(starting_balance=483.90, max_account_drawdown_pct=0.15)
    risk = RiskManager(risk_cfg)
    risk.set_ath_equity(600.0)

    risk.anchor_on_start(483.90)

    assert risk.ath_equity == 483.90
    assert not risk.halted
    # Tras re-anclar, el primer register_equity al mismo equity no debe halt.
    risk.register_equity(483.90)
    assert not risk.halted


def test_anchor_on_start_clears_stale_halt():
    risk_cfg = RiskConfig(starting_balance=483.90, max_account_drawdown_pct=0.15)
    risk = RiskManager(risk_cfg)
    risk.set_ath_equity(600.0)
    risk.register_equity(483.90)          # dispara el disyuntor con el pico viejo
    assert risk.halted and risk.halted_reason == "drawdown_cuenta"

    risk.anchor_on_start(483.90)          # arranque del servicio (equity == base)
    assert not risk.halted
    assert risk.halted_reason == ""


def test_anchor_on_start_keeps_peak_within_tolerance():
    # Drawdown importado del 5% (< 15%): pico legítimo, se conserva (anti-gaming).
    risk_cfg = RiskConfig(starting_balance=1000.0, max_account_drawdown_pct=0.15)
    risk = RiskManager(risk_cfg)
    risk.set_ath_equity(1000.0)

    risk.anchor_on_start(950.0)

    assert risk.ath_equity == 1000.0
    # Un bleed adicional que cruce el límite sí debe seguir disparando.
    risk.register_equity(840.0)           # 16% desde 1000 -> halt
    assert risk.halted and risk.halted_reason == "drawdown_cuenta"


def test_anchor_on_start_real_loss_below_baseline_stays_armed():
    # Discriminador: equity de arranque POR DEBAJO de la base (pérdida real de
    # principal). Aunque el drawdown importado supere el límite, NO se desarma:
    # el máximo se ancla a la base y el disyuntor salta con el drawdown real.
    risk_cfg = RiskConfig(starting_balance=1000.0, max_account_drawdown_pct=0.15)
    risk = RiskManager(risk_cfg)
    risk.set_ath_equity(1000.0)

    risk.anchor_on_start(800.0)           # 20% por debajo de la base: pérdida real

    assert risk.ath_equity == 1000.0      # anclado a la base, NO re-anclado a 800
    risk.register_equity(800.0)
    assert risk.halted and risk.halted_reason == "drawdown_cuenta"


def test_anchor_on_start_ignores_foreign_peak_but_arms_from_baseline():
    # Pico ajeno (600, de un capital viejo) + pérdida real por debajo de la base
    # (equity 400 < base 483.90). Se ignora el pico ajeno pero se mide desde la
    # base: 17.3% de caída -> debe halt.
    risk_cfg = RiskConfig(starting_balance=483.90, max_account_drawdown_pct=0.15)
    risk = RiskManager(risk_cfg)
    risk.set_ath_equity(600.0)

    risk.anchor_on_start(400.0)

    assert risk.ath_equity == 483.90      # anclado a la base, no a 600 ni a 400
    risk.register_equity(400.0)           # (483.90-400)/483.90 = 17.3% -> halt
    assert risk.halted and risk.halted_reason == "drawdown_cuenta"


def test_anchor_on_start_small_real_loss_below_baseline_no_halt():
    # Pérdida real pequeña (2%) por debajo de la base con pico ajeno alto: no debe
    # halt, pero queda armado midiendo desde la base.
    risk_cfg = RiskConfig(starting_balance=483.90, max_account_drawdown_pct=0.15)
    risk = RiskManager(risk_cfg)
    risk.set_ath_equity(600.0)

    risk.anchor_on_start(474.0)           # ~2% por debajo de la base

    assert risk.ath_equity == 483.90
    risk.register_equity(474.0)
    assert not risk.halted


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
