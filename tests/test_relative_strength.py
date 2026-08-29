import pytest
import pandas as pd
from unittest.mock import MagicMock
from tradebot.relative_strength import compute_rs_rankings, select_top_symbols
from tradebot.config import Config, Instrument, RiskConfig
from tradebot.engine import Engine
from tradebot.risk import RiskManager
from tradebot.storage import Storage

def test_compute_rs_rankings():
    exchange = MagicMock()
    
    # 14d return: BTC +10%, SOL +30%, AVAX +5%
    def mock_ohlcv(symbol, timeframe="1d", limit=16):
        if symbol == "BTC/USDT":
            prices = [100.0] * 15 + [110.0]
        elif symbol == "SOL/USDT":
            prices = [100.0] * 15 + [130.0]
        elif symbol == "AVAX/USDT":
            prices = [100.0] * 15 + [105.0]
        else:
            prices = [100.0] * 16
        df = pd.DataFrame({"close": prices})
        return df

    exchange.fetch_ohlcv.side_effect = mock_ohlcv

    rankings = compute_rs_rankings(exchange, pool=["SOL/USDT", "AVAX/USDT", "BTC/USDT"], benchmark_symbol="BTC/USDT", lookback_days=14)
    
    # SOL RS = 30% - 10% = +20%
    # AVAX RS = 5% - 10% = -5%
    assert rankings["SOL/USDT"] == 20.0
    assert rankings["AVAX/USDT"] == -5.0
    assert list(rankings.keys())[0] == "SOL/USDT"

def test_select_top_symbols_hysteresis():
    # Actualmente activos: SOL/USDT y AVAX/USDT
    current = ["SOL/USDT", "AVAX/USDT"]
    
    # Rankings: SUI es +12%, SOL es +10%, AVAX es +6%
    # Con histéresis del 5%:
    # SUI (+12%) vs SOL (+10%): 12% - 10% = 2% (< 5%), no reemplaza a SOL!
    # SUI (+12%) vs AVAX (+6%): 12% - 6% = 6% (> 5%), reemplaza a AVAX!
    rankings = {
        "SUI/USDT": 12.0,
        "SOL/USDT": 10.0,
        "AVAX/USDT": 6.0,
        "ADA/USDT": 1.0,
    }

    selected = select_top_symbols(current, rankings, top_k=2, hysteresis_pct=5.0)
    assert selected == ["SOL/USDT", "SUI/USDT"]

def test_engine_update_head_symbols(tmp_path):
    db_path = str(tmp_path / "test.db")
    storage = Storage(db_path)

    config = MagicMock(spec=Config)
    config.risk = RiskConfig(starting_balance=1000.0, quote_currency="USDT")
    config.mode = "paper"
    config.effective_db_path.return_value = db_path

    inst1 = Instrument(
        symbol="SOL/USDT", category="breakout_diario", strategy_name="breakout",
        strategy_params={"lookback": 20}, stop_loss_pct=0.08, take_profit_pct=0.30, position_size_pct=0.20
    )
    inst2 = Instrument(
        symbol="AVAX/USDT", category="breakout_diario", strategy_name="breakout",
        strategy_params={"lookback": 20}, stop_loss_pct=0.08, take_profit_pct=0.30, position_size_pct=0.20
    )
    config.instruments = [inst1, inst2]

    execution = MagicMock()
    rm = RiskManager(config.risk)

    engine = Engine(config, {"SOL/USDT": MagicMock(), "AVAX/USDT": MagicMock()}, rm, execution, storage)

    # Actualizar la cabeza a SUI/USDT y SOL/USDT
    engine.update_head_symbols("breakout_diario", ["SOL/USDT", "SUI/USDT"])

    syms = [i.symbol for i in engine.config.instruments if i.category == "breakout_diario"]
    assert "SUI/USDT" in syms
    assert "SOL/USDT" in syms
    assert "SUI/USDT" in engine.strategies
