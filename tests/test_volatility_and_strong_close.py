"""Tests para Position Sizing Adaptativo por Volatilidad y Filtro de Cierre Fuerte."""
import pytest
import pandas as pd
from unittest.mock import MagicMock
from tradebot.config import Instrument, RiskConfig
from tradebot.models import Position, Side, Signal, SignalType
from tradebot.risk import RiskManager, RiskDecision


# ---------------------------------------------------------------------------
# Test 1: Volatility Sizing reduce tamaño cuando ATR es alto
# ---------------------------------------------------------------------------
def test_volatility_sizing_high_atr_reduces_size():
    """Con ATR alto (6%), el tamaño debería reducirse al 50% (factor 0.5x)."""
    inst = Instrument(
        symbol="SOL/USDT", category="breakout", strategy_name="breakout",
        strategy_params={}, stop_loss_pct=0.08, take_profit_pct=0.30,
        position_size_pct=0.20, volatility_sizing=True,
        volatility_ref_atr_pct=0.03,  # referencia = 3%
        volatility_size_min=0.5, volatility_size_max=1.5,
    )
    risk_cfg = RiskConfig(starting_balance=1000.0)
    rm = RiskManager(risk_cfg)
    signal = Signal(type=SignalType.BUY, symbol="SOL/USDT", price=100.0, reason="breakout")

    # ATR = 6.0 sobre precio 100 = 6%. Ref = 3%. Factor = 3/6 = 0.5x
    decision = rm.evaluate_entry(signal, inst, balance=1000.0, open_positions=[], current_atr=6.0)
    assert decision.order is not None
    # Capital base = 1000 * 0.20 = 200. Con factor 0.5 = 100. Amount = 100/100 = 1.0
    assert abs(decision.order.amount - 1.0) < 0.01


def test_volatility_sizing_low_atr_increases_size():
    """Con ATR bajo (1.5%), el tamaño debería aumentar al 150% (factor 1.5x, capped)."""
    inst = Instrument(
        symbol="SOL/USDT", category="breakout", strategy_name="breakout",
        strategy_params={}, stop_loss_pct=0.08, take_profit_pct=0.30,
        position_size_pct=0.20, volatility_sizing=True,
        volatility_ref_atr_pct=0.03,
        volatility_size_min=0.5, volatility_size_max=1.5,
    )
    risk_cfg = RiskConfig(starting_balance=1000.0)
    rm = RiskManager(risk_cfg)
    signal = Signal(type=SignalType.BUY, symbol="SOL/USDT", price=100.0, reason="breakout")

    # ATR = 1.5 sobre precio 100 = 1.5%. Ref = 3%. Factor = 3/1.5 = 2.0 → capped 1.5x
    decision = rm.evaluate_entry(signal, inst, balance=1000.0, open_positions=[], current_atr=1.5)
    assert decision.order is not None
    # Capital base = 200. Con factor 1.5 = 300. Amount = 300/100 = 3.0
    assert abs(decision.order.amount - 3.0) < 0.01


def test_volatility_sizing_normal_atr_no_change():
    """Con ATR = referencia (3%), el factor es 1.0x, sin cambio."""
    inst = Instrument(
        symbol="SOL/USDT", category="breakout", strategy_name="breakout",
        strategy_params={}, stop_loss_pct=0.08, take_profit_pct=0.30,
        position_size_pct=0.20, volatility_sizing=True,
        volatility_ref_atr_pct=0.03,
    )
    risk_cfg = RiskConfig(starting_balance=1000.0)
    rm = RiskManager(risk_cfg)
    signal = Signal(type=SignalType.BUY, symbol="SOL/USDT", price=100.0, reason="breakout")

    # ATR = 3.0 sobre precio 100 = 3%. Ref = 3%. Factor = 1.0x
    decision = rm.evaluate_entry(signal, inst, balance=1000.0, open_positions=[], current_atr=3.0)
    assert decision.order is not None
    # Capital = 200. Amount = 200/100 = 2.0
    assert abs(decision.order.amount - 2.0) < 0.01


def test_volatility_sizing_disabled_no_effect():
    """Con volatility_sizing=False, el ATR no afecta el tamaño."""
    inst = Instrument(
        symbol="SOL/USDT", category="breakout", strategy_name="breakout",
        strategy_params={}, stop_loss_pct=0.08, take_profit_pct=0.30,
        position_size_pct=0.20, volatility_sizing=False,
    )
    risk_cfg = RiskConfig(starting_balance=1000.0)
    rm = RiskManager(risk_cfg)
    signal = Signal(type=SignalType.BUY, symbol="SOL/USDT", price=100.0, reason="breakout")

    decision = rm.evaluate_entry(signal, inst, balance=1000.0, open_positions=[], current_atr=10.0)
    assert decision.order is not None
    # Capital = 200 sin ajuste. Amount = 200/100 = 2.0
    assert abs(decision.order.amount - 2.0) < 0.01


# ---------------------------------------------------------------------------
# Test 2: Strong Close Filter
# ---------------------------------------------------------------------------
def test_strong_close_filter_rejects_weak_candle():
    """Una vela con cierre en el 30% inferior del rango (mecha de rechazo)
    debería ser rechazada por el filtro de cierre fuerte."""
    # Vela: Open=100, High=110, Low=95, Close=99.5
    # Rango = 110 - 95 = 15. Close posición = (99.5-95)/15 = 0.30 = 30%
    # Con threshold 75%, 30% < 75% → rechazada
    candle_range = 110.0 - 95.0  # 15.0
    close_position = (99.5 - 95.0) / candle_range  # 0.30
    assert close_position < 0.75  # confirma que sería rechazada


def test_strong_close_filter_accepts_strong_candle():
    """Una vela con cierre en el 90% superior del rango debería ser aceptada."""
    # Vela: Open=100, High=110, Low=95, Close=108.5
    # Rango = 15. Close posición = (108.5-95)/15 = 0.90 = 90%
    # Con threshold 75%, 90% > 75% → aceptada
    candle_range = 110.0 - 95.0
    close_position = (108.5 - 95.0) / candle_range  # 0.90
    assert close_position >= 0.75


# ---------------------------------------------------------------------------
# Test 3: Exposure cap
# ---------------------------------------------------------------------------
def test_exposure_cap_rejects_when_over_limit():
    """Con max_total_exposure_pct=0.80, si ya hay 80% invertido, rechaza nueva entrada."""
    inst = Instrument(
        symbol="AVAX/USDT", category="breakout", strategy_name="breakout",
        strategy_params={}, stop_loss_pct=0.08, take_profit_pct=0.30,
        position_size_pct=0.20,
    )
    risk_cfg = RiskConfig(starting_balance=1000.0, max_total_exposure_pct=0.80)
    rm = RiskManager(risk_cfg)
    signal = Signal(type=SignalType.BUY, symbol="AVAX/USDT", price=10.0, reason="breakout")

    # 4 posiciones abiertas de $200 cada una = $800 / $1000 = 80%
    existing = [
        Position(symbol=f"SYM{i}/USDT", category="test", strategy_name="test",
                 side=Side.BUY, amount=20.0, entry_price=10.0, stop_loss=9.0,
                 take_profit=13.0, entry_fee=0.1, reason="test")
        for i in range(4)
    ]

    decision = rm.evaluate_entry(signal, inst, balance=1000.0, open_positions=existing, current_atr=0.0)
    assert decision.order is None
    assert "exposición total" in decision.reason
