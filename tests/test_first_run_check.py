"""La verificación de API en el arranque debe ejecutarse SOLO una vez (marca en
disco) y solo en modo live."""

from conftest import make_config, make_instrument

from tradebot import daemon
from tradebot.notifier import NullNotifier


class _FakeExchange:
    def __init__(self):
        self.calls = []

    def create_market_buy(self, symbol, cost):
        self.calls.append(("buy", symbol, cost))
        return {"filled": cost / 2.0, "average": 2.0, "cost": cost}

    def create_market_sell(self, symbol, amount):
        self.calls.append(("sell", symbol, amount))
        return {"filled": amount, "average": 1.99, "cost": amount * 1.99}


class _FakeEngine:
    def __init__(self, exchange):
        self.exchange = exchange
        self.notifier = NullNotifier()


def _live_config():
    cfg = make_config(make_instrument())
    cfg.mode = "live"
    return cfg


def test_first_run_check_runs_once_and_marks(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "API_CHECK_MARKER", str(tmp_path / ".api_verified"))
    ex = _FakeExchange()
    engine = _FakeEngine(ex)

    daemon._maybe_first_run_api_check(engine, _live_config())
    assert [c[0] for c in ex.calls] == ["buy", "sell"]      # hizo el round-trip

    ex.calls.clear()
    daemon._maybe_first_run_api_check(engine, _live_config())
    assert ex.calls == []                                    # ya no repite


def test_no_check_in_paper_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "API_CHECK_MARKER", str(tmp_path / ".api_verified"))
    ex = _FakeExchange()
    daemon._maybe_first_run_api_check(_FakeEngine(ex), make_config(make_instrument()))
    assert ex.calls == []                                    # paper -> no verifica
