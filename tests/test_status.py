"""Status estructurado del bot (para publicar al gist)."""

import json

from conftest import make_config, make_instrument

from tradebot import status
from tradebot.engine import Engine
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.mean_reversion import MeanReversionStrategy


def _engine(config):
    strat = MeanReversionStrategy(rsi_period=14, rsi_oversold=30, bb_period=20, bb_std=2.0)
    return Engine(config, {config.instruments[0].symbol: strat}, RiskManager(config.risk),
                  PaperExecutionEngine(config), Storage(":memory:"), enforce_daily_loss=False)


def test_active_heads_groups_by_category():
    cfg = make_config(make_instrument(symbol="BNB/USDT", category="momentum1d"))
    cfg.instruments.append(make_instrument(symbol="ADA/USDT", category="momentum1d"))
    cfg.instruments.append(make_instrument(symbol="SOL/USDT", category="breakout1d"))
    heads = status.active_heads(cfg)
    assert [h["name"] for h in heads] == ["momentum1d", "breakout1d"]
    mom = heads[0]
    assert mom["symbols"] == ["BNB/USDT", "ADA/USDT"]


def test_build_status_has_core_fields():
    cfg = make_config(make_instrument(symbol="BNB/USDT", category="momentum1d"))
    cfg.sniper.enabled = True
    cfg.carry.enabled = False
    st = status.build_status(_engine(cfg), cfg)
    for k in ("timestamp", "mode", "equity", "closed_trades", "pnl_abs",
              "win_rate", "heads", "by_head", "sniper_enabled", "carry_enabled"):
        assert k in st
    assert st["closed_trades"] == 0
    assert st["sniper_enabled"] is True
    assert st["carry_enabled"] is False
    assert st["heads"][0]["name"] == "momentum1d"


def test_load_merged_merges_sniper(tmp_path):
    sp, sn = tmp_path / "status.json", tmp_path / "sniper.json"
    sp.write_text(json.dumps({"mode": "paper", "equity": 1000.0}))
    sn.write_text(json.dumps({"open": 3, "pnl": -1.2}))
    merged = status.load_merged(str(sp), str(sn))
    assert merged["equity"] == 1000.0
    assert merged["sniper"]["open"] == 3
