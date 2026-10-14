"""Cambio automático de la fuente de señales: si la principal (p. ej. KuCoin) deja de
responder, las velas salen del respaldo (p. ej. Binance) y se vuelve a la principal cuando
responde. Las ventas no dependen de esto: usan los precios del exchange que opera."""

from unittest.mock import MagicMock

import ccxt
import pytest

from tradebot import exchange as exchange_mod
from tradebot.config import Config, Credentials, RiskConfig
from tradebot.exchange import DATA_FAILOVER_AFTER, DATA_FAILOVER_SECONDS, Exchange
from tradebot.status import build_status

SYMBOL = "NEAR/USDC"
ROW = [[1_700_000_000_000, 5.0, 5.0, 5.0, 5.0, 10.0]]


@pytest.fixture
def clock(monkeypatch):
    t = {"now": 1000.0}
    monkeypatch.setattr(exchange_mod.time, "monotonic", lambda: t["now"])
    return t


def _exchange(monkeypatch):
    built = {}
    for name in ("myokx", "kucoin", "binance"):
        def factory(params, n=name):
            client = MagicMock(name=n)
            client.fetch_ohlcv.return_value = ROW
            built[n] = client
            return client
        monkeypatch.setattr(ccxt, name, factory)
    config = Config(exchange="myokx", risk=RiskConfig(quote_currency="USDC"), credentials=Credentials("k", "s", "p"),
                    data_exchange="kucoin", data_quote="USDT", data_fallback_exchange="binance", data_fallback_quote="USDT")
    return Exchange(config), built


def _pairs(client):
    return [c.args[0] for c in client.fetch_ohlcv.call_args_list]


def test_primary_source_is_used_while_it_answers(monkeypatch, clock):
    ex, built = _exchange(monkeypatch)

    ex.fetch_ohlcv(SYMBOL, "4h", 300)

    assert _pairs(built["kucoin"]) == ["NEAR/USDT"] and _pairs(built["binance"]) == []
    assert ex.active_data_source == "kucoin"


def test_one_failure_uses_the_backup_for_that_call_only(monkeypatch, clock):
    ex, built = _exchange(monkeypatch)
    built["kucoin"].fetch_ohlcv.side_effect = [ccxt.NetworkError("timeout"), ROW]

    ex.fetch_ohlcv(SYMBOL, "4h", 300)                                   # sale de Binance
    ex.fetch_ohlcv(SYMBOL, "4h", 300)                                   # KuCoin otra vez

    assert _pairs(built["binance"]) == ["NEAR/USDT"]
    assert len(_pairs(built["kucoin"])) == 2 and ex.active_data_source == "kucoin"


def test_repeated_failures_switch_to_the_backup_and_come_back(monkeypatch, clock, caplog):
    ex, built = _exchange(monkeypatch)
    built["kucoin"].fetch_ohlcv.side_effect = ccxt.ExchangeNotAvailable("403 región restringida")

    for _ in range(DATA_FAILOVER_AFTER):
        ex.fetch_ohlcv(SYMBOL, "4h", 300)
    assert ex.active_data_source == "binance"
    assert any("no responde" in r.getMessage() for r in caplog.records)

    calls = len(_pairs(built["kucoin"]))
    ex.fetch_ohlcv(SYMBOL, "4h", 300)                                   # durante la pausa ni se prueba KuCoin
    assert len(_pairs(built["kucoin"])) == calls

    clock["now"] += DATA_FAILOVER_SECONDS + 1                           # pasada la pausa, se vuelve a probar
    ex.fetch_ohlcv(SYMBOL, "4h", 300)
    assert len(_pairs(built["kucoin"])) == calls + 1 and ex.active_data_source == "binance"   # sigue caída

    clock["now"] += DATA_FAILOVER_SECONDS + 1
    built["kucoin"].fetch_ohlcv.side_effect = None                     # KuCoin responde
    ex.fetch_ohlcv(SYMBOL, "4h", 300)
    assert ex.active_data_source == "kucoin"
    assert any("vuelve a responder" in r.getMessage() for r in caplog.records)


def test_a_pair_missing_in_the_primary_does_not_switch_everything(monkeypatch, clock):
    ex, built = _exchange(monkeypatch)
    built["kucoin"].fetch_ohlcv.side_effect = ccxt.BadSymbol("par no listado")

    for _ in range(DATA_FAILOVER_AFTER + 2):
        ex.fetch_ohlcv(SYMBOL, "4h", 300)

    assert ex.active_data_source == "kucoin"                           # no es una caída de KuCoin
    assert len(_pairs(built["binance"])) == DATA_FAILOVER_AFTER + 2


def test_both_sources_failing_raises(monkeypatch, clock):
    ex, built = _exchange(monkeypatch)
    built["kucoin"].fetch_ohlcv.side_effect = ccxt.NetworkError("caído")
    built["binance"].fetch_ohlcv.side_effect = ccxt.NetworkError("también caído")
    monkeypatch.setattr(exchange_mod.time, "sleep", lambda s: None)    # sin esperar los reintentos

    with pytest.raises(ccxt.NetworkError, match="también"):
        ex.fetch_ohlcv(SYMBOL, "4h", 300)


def test_history_also_uses_the_backup(monkeypatch, clock):
    ex, built = _exchange(monkeypatch)
    built["kucoin"].fetch_ohlcv.side_effect = ccxt.NetworkError("timeout")
    built["binance"].parse_timeframe = lambda tf: 900
    built["binance"].milliseconds = lambda: 1_700_000_000_000 + 900_000

    df = ex.fetch_ohlcv_history(SYMBOL, "15m", 1)

    assert len(df) == 1 and _pairs(built["binance"]) == ["NEAR/USDT"]


def test_without_backup_nothing_changes(monkeypatch, clock):
    ex, built = _exchange(monkeypatch)
    ex._fallback = None
    built["kucoin"].fetch_ohlcv.side_effect = ccxt.BadSymbol("par no listado")
    with pytest.raises(ccxt.BadSymbol):
        ex.fetch_ohlcv(SYMBOL, "4h", 300)
    assert ex.active_data_source == "kucoin"


def test_status_reports_the_active_source(monkeypatch, clock):
    ex, _ = _exchange(monkeypatch)
    engine = MagicMock()
    engine.exchange = ex
    engine.positions = []
    engine.storage.summary.return_value = {"trades": 0, "pnl_abs": 0.0, "win_rate": 0.0, "avg_pnl_pct": 0.0}
    engine.storage.stop_slippage.return_value = {"stops": 0, "avg_pct": 0.0, "worst_pct": 0.0}
    engine.equity.return_value = 100.0
    engine.paused_heads.return_value = {}
    assert build_status(engine, ex.config)["data_source"] == "kucoin"
