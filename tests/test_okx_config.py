"""config.yaml en OKX Europa (desde el cambio de octubre de 2026) y la comprobación de comisiones."""

import sys
from dataclasses import asdict
from pathlib import Path

from tradebot.config import load_config

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from check_fees import summarize  # noqa: E402

ENV = ("KUCOIN_API_KEY", "KUCOIN_API_SECRET", "KUCOIN_API_PASSPHRASE", "BYBIT_API_KEY", "BYBIT_API_SECRET",
       "OKX_API_KEY", "OKX_API_SECRET", "OKX_API_PASSPHRASE")


def test_live_config_runs_on_okx_with_kucoin_signals(monkeypatch):
    monkeypatch.setattr("tradebot.config.load_dotenv", lambda *a, **k: None)
    for name in ENV:
        monkeypatch.setenv(name, "x")
    bybit, okx = load_config("config.bybiteu.yaml"), load_config("config.yaml")

    assert (okx.mode, okx.exchange, okx.risk.quote_currency) == ("live", "myokx", "USDC")
    assert (okx.data_exchange, okx.data_quote, okx.data_fallback_exchange, okx.data_fallback_quote) == ("kucoin", "USDT", "binance", "USDT")
    assert okx.signals_elsewhere and okx.data_symbol("NEAR/USDC") == "NEAR/USDT"
    assert okx.engine.fee_pct == 0.001 and okx.engine.exchange_stops is True
    assert okx.credentials.needs_passphrase is True and okx.credentials.is_complete
    assert okx.carry.funding_radar_enabled is False

    same = lambda c: [{k: v for k, v in asdict(i).items()} for i in c.instruments]
    assert same(okx) == same(bybit)
    assert asdict(okx.risk) == asdict(bybit.risk)
    differ = dict(fee_pct=None, exchange_stops=None)
    assert dict(asdict(okx.engine), **differ) == dict(asdict(bybit.engine), **differ)
    assert (okx.timeframe, okx.lookback, okx.disabled_heads) == (bybit.timeframe, bybit.lookback, bybit.disabled_heads)


def test_fee_summary_says_how_the_account_compares():
    flat = {s: {"taker": 0.001, "maker": 0.0008} for s in ("BTC/USDC", "NEAR/USDC")}
    lines = summarize(flat, expected=0.001)
    assert lines[0] == "Todos los pares pagan lo mismo a mercado: 0.100%"
    assert "KuCoin (el de siempre), 0.10%: lo mismo" in lines[1] and "Bybit EU (comprobado el 2026-10-14), 0.25%: menos" in lines[2]
    assert lines[-1].startswith("RESULTADO: comisión igual o menor")

    spot_only = {"BTC/USDC": {"taker": 0.002, "maker": 0.001}, "NEAR/USDC": {"taker": 0.0035, "maker": 0.002}}
    lines = summarize(spot_only, expected=0.001)
    assert lines[0] == "La comisión a mercado varía por par: de 0.200% a 0.350%"
    assert "Bybit EU (comprobado el 2026-10-14), 0.25%: más" in lines[2]
    assert lines[-1].startswith("RESULTADO: comisión MAYOR")
