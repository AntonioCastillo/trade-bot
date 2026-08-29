import pytest
from unittest.mock import MagicMock, patch
import pandas as pd

from tradebot.config import Config, XSMomConfig, RiskConfig
from tradebot.xsmom import LiveXSMomFuturesExecutor


def _futures_cfg():
    config = MagicMock(spec=Config)
    config.mode = "live"
    config.risk = RiskConfig(quote_currency="USDT")
    config.xsmom = XSMomConfig(
        enabled=True, universe=["BTC/USDT"], fee_pct=0.001,
        leverage=2.0, max_notional_usdt=100.0, liquidation_buffer_pct=0.15,
    )
    return config


def test_guard_liquidations_closes_and_notifies_when_near():
    config = _futures_cfg()
    exchange = MagicMock()
    exchange._normalize_symbol = MagicMock(return_value="BTC/USDT:USDT")
    # Mark 1000, liquidación 950 -> dist 5% < buffer 15% -> cierre de emergencia.
    exchange._client.fetch_position = MagicMock(return_value={
        "contracts": 100.0, "markPrice": 1000.0, "liquidationPrice": 950.0, "side": "long",
    })
    notifier = MagicMock()

    executor = LiveXSMomFuturesExecutor(
        config, exchange, ["BTC/USDT"], dry_run=False, notifier=notifier,
    )
    executor.guard_liquidations()

    exchange.create_futures_order.assert_called_once_with("BTC/USDT", "sell", 100.0, leverage=2.0)
    notifier.notify.assert_called_once()   # #5: la alerta SÍ dispara


def test_guard_liquidations_noop_when_far():
    config = _futures_cfg()
    exchange = MagicMock()
    exchange._normalize_symbol = MagicMock(return_value="BTC/USDT:USDT")
    # Mark 1000, liquidación 500 -> dist 50% > buffer -> no toca nada.
    exchange._client.fetch_position = MagicMock(return_value={
        "contracts": 100.0, "markPrice": 1000.0, "liquidationPrice": 500.0, "side": "long",
    })
    notifier = MagicMock()

    executor = LiveXSMomFuturesExecutor(
        config, exchange, ["BTC/USDT"], dry_run=False, notifier=notifier,
    )
    executor.guard_liquidations()

    exchange.create_futures_order.assert_not_called()
    notifier.notify.assert_not_called()


def test_guard_liquidations_skips_in_dry_run():
    config = _futures_cfg()
    exchange = MagicMock()
    executor = LiveXSMomFuturesExecutor(config, exchange, ["BTC/USDT"], dry_run=True)
    executor.guard_liquidations()
    exchange._client.fetch_position.assert_not_called()


def test_xsmom_futures_executor_dry_run():
    config = MagicMock(spec=Config)
    config.mode = "live"
    
    risk_cfg = RiskConfig(quote_currency="USDT")
    config.risk = risk_cfg
    
    xsmom_cfg = XSMomConfig(
        enabled=True,
        universe=["BTC/USDT", "ETH/USDT"],
        fee_pct=0.001,
        leverage=2.0,
        max_notional_usdt=100.0,
        liquidation_buffer_pct=0.15,
    )
    config.xsmom = xsmom_cfg
    
    exchange = MagicMock()
    exchange._client.fetch_balance = MagicMock(return_value={
        "total": {"USDT": 1000.0},
        "free": {"USDT": 1000.0},
    })
    # Mockear posiciones abiertas
    exchange._client.fetch_positions = MagicMock(return_value=[])
    exchange._client.fetch_position = MagicMock(return_value=None)
    
    # Mockear contract size
    exchange.contract_size = MagicMock(return_value=0.001)
    
    executor = LiveXSMomFuturesExecutor(
        config, exchange, ["BTC/USDT", "ETH/USDT"], dry_run=True
    )
    
    assert executor.equity({}) == 1000.0
    assert executor._positions() == {}
    
    prices = {"BTC/USDT": 60000.0, "ETH/USDT": 3000.0}
    targets = ["BTC/USDT"]
    
    fee = executor.rebalance(targets, prices)
    exchange.create_futures_order.assert_not_called()


def test_xsmom_futures_executor_rebalance_real_limits_and_units():
    config = MagicMock(spec=Config)
    config.mode = "live"
    
    risk_cfg = RiskConfig(quote_currency="USDT")
    config.risk = risk_cfg
    
    # 1. leverage=2x, max_notional=100 USDT
    xsmom_cfg = XSMomConfig(
        enabled=True,
        universe=["BTC/USDT", "ETH/USDT"],
        fee_pct=0.001,
        leverage=2.0,
        max_notional_usdt=100.0,
        liquidation_buffer_pct=0.15,
    )
    config.xsmom = xsmom_cfg
    
    exchange = MagicMock()
    # Total equity = 500 USDT.
    # Con leverage 2.0x, per_target es (500 * 2.0) / 1 = 1000 USDT.
    # Pero max_notional_usdt lo topa a 100.0 USDT!
    exchange._client.fetch_balance = MagicMock(return_value={
        "total": {"USDT": 500.0},
        "free": {"USDT": 500.0},
    })
    
    # Posición actual: ya tenemos 100 contratos de BTC/USDT abiertos
    exchange._client.fetch_positions = MagicMock(return_value=[
        {"symbol": "BTC/USDT:USDT", "contracts": 100.0, "side": "long"}
    ])
    exchange._client.fetch_position = MagicMock(return_value=None)
    exchange.contract_size = MagicMock(return_value=0.001)
    
    executor = LiveXSMomFuturesExecutor(
        config, exchange, ["BTC/USDT", "ETH/USDT"], dry_run=False
    )
    
    prices = {"BTC/USDT": 1000.0}  # precio bajo para simplificar cálculo
    # target size en monedas: 100 USDT limit / 1000.0 = 0.1 BTC
    # target contracts: 0.1 BTC / 0.001 = 100 contratos
    # current contracts: 100.0 (ya tenemos 100 contratos abiertos)
    # diff: 100 - 100 = 0. No debería enviar ninguna orden!
    
    targets = ["BTC/USDT"]
    executor.rebalance(targets, prices)
    
    # Verificar que no envía orden de ajuste porque ya está en el tamaño objetivo correcto!
    # (Si el bug de división persistiera, current_contracts sería 100 / 0.001 = 100,000, 
    # y enviaría una venta masiva para reducir la posición, lo cual fallaría esta prueba).
    exchange.create_futures_order.assert_not_called()
