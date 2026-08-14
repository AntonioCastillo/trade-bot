import pytest
from unittest.mock import MagicMock, patch
import pandas as pd

from tradebot.config import Config, XSMomConfig, RiskConfig
from tradebot.xsmom import LiveXSMomFuturesExecutor


def test_xsmom_futures_executor_dry_run():
    # 1. Configurar mocks
    config = MagicMock(spec=Config)
    config.mode = "live"
    
    risk_cfg = RiskConfig(quote_currency="USDT")
    config.risk = risk_cfg
    
    xsmom_cfg = XSMomConfig(
        enabled=True,
        universe=["BTC/USDT", "ETH/USDT"],
        fee_pct=0.001,
        leverage=2.0,
    )
    config.xsmom = xsmom_cfg
    
    exchange = MagicMock()
    # Mockear fetch_balance de CCXT para devolver equity de 1000 USDT
    exchange._client.fetch_balance = MagicMock(return_value={
        "total": {"USDT": 1000.0},
        "free": {"USDT": 1000.0},
    })
    # Mockear posiciones abiertas
    exchange._client.fetch_positions = MagicMock(return_value=[])
    
    # Mockear contract size
    exchange.contract_size = MagicMock(return_value=0.001)
    
    executor = LiveXSMomFuturesExecutor(
        config, exchange, ["BTC/USDT", "ETH/USDT"], dry_run=True
    )
    
    # 2. Verificar lectura de balance y posiciones
    assert executor.equity({}) == 1000.0
    assert executor._positions() == {}
    
    # 3. Lanzar rebalanceo en dry-run (no debe enviar órdenes al exchange)
    prices = {"BTC/USDT": 60000.0, "ETH/USDT": 3000.0}
    # Targets: BTC/USDT (top-1 de nuestra cesta)
    targets = ["BTC/USDT"]
    
    fee = executor.rebalance(targets, prices)
    
    # En dry-run el exchange no debe recibir ninguna orden de creación
    exchange.create_futures_order.assert_not_called()
