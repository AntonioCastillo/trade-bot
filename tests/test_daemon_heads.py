"""El resumen de cabezas activas (arranque + heartbeat) lista cabezas y subsistemas."""

from conftest import make_config, make_instrument

from tradebot import daemon


def test_heads_summary_groups_and_flags():
    cfg = make_config(make_instrument(symbol="BNB/USDT", category="momentum1d"))
    cfg.instruments.append(make_instrument(symbol="ADA/USDT", category="momentum1d"))
    cfg.instruments.append(make_instrument(symbol="SOL/USDT", category="breakout1d"))
    cfg.sniper.enabled = True
    cfg.carry.enabled = False

    out = daemon._heads_summary(cfg)
    assert "momentum1d: BNB, ADA" in out     # agrupa símbolos por cabeza
    assert "breakout1d: SOL" in out
    assert "sniper" in out                    # subsistema activo aparece
    assert "carry" not in out                 # apagado no aparece


def test_heads_summary_includes_carry_when_enabled():
    cfg = make_config(make_instrument(symbol="BTC/USDT", category="trend1d"))
    cfg.sniper.enabled = False
    cfg.carry.enabled = True
    out = daemon._heads_summary(cfg)
    assert "trend1d: BTC" in out
    assert "carry" in out
    assert "sniper" not in out
