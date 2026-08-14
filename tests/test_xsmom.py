"""Momentum transversal: ranking, gate de tendencia, y contabilidad de la cartera."""

import numpy as np
import pandas as pd
from conftest import make_config, make_instrument

from tradebot import daemon
from tradebot.config import XSMomConfig
from tradebot.notifier import NullNotifier
from tradebot.xsmom import (XSMOM_LIVE_CONFIRM, XSMOM_LIVE_CONFIRM_ENV, LiveXSMomExecutor,
                            XSMomPortfolio, XSMomRunner, rank_momentum, select_targets, trend_bull)


class _FakeExLive:
    """Exchange falso que SIMULA balances (venta añade USDT, compra lo resta)."""
    def __init__(self, balances, price=10.0):
        self._bal = dict(balances)
        self.price = price
        self.buys, self.sells = [], []

    def fetch_balances_total(self):
        return dict(self._bal)

    def fetch_balance(self, cur):
        return self._bal.get(cur, 0.0)

    def amount_to_precision(self, sym, amt):
        return amt

    def create_market_sell(self, sym, amt):
        self.sells.append((sym, amt))
        base = sym.split("/")[0]
        self._bal[base] = self._bal.get(base, 0.0) - amt
        self._bal["USDT"] = self._bal.get("USDT", 0.0) + amt * self.price

    def create_market_buy(self, sym, cost):
        self.buys.append((sym, cost))
        self._bal["USDT"] = self._bal.get("USDT", 0.0) - cost
        self._bal[sym.split("/")[0]] = self._bal.get(sym.split("/")[0], 0.0) + cost / self.price


def _series(vals):
    idx = pd.date_range("2024-01-01", periods=len(vals), freq="1D", tz="UTC")
    return pd.Series(vals, index=idx)


def test_rank_momentum_orders_desc():
    closes = {
        "A/USDT": _series([100] * 40 + [130]),   # +30%
        "B/USDT": _series([100] * 40 + [110]),   # +10%
        "C/USDT": _series([100] * 40 + [90]),    # -10%
    }
    ranked = rank_momentum(closes, lookback=30)
    assert [s for s, _ in ranked] == ["A/USDT", "B/USDT", "C/USDT"]


def test_rank_skips_short_history():
    closes = {"A/USDT": _series([100, 110]), "B/USDT": _series([100] * 40 + [120])}
    ranked = rank_momentum(closes, lookback=30)
    assert [s for s, _ in ranked] == ["B/USDT"]     # A no tiene 30 velas


def test_trend_bull_gate():
    up = _series(list(np.linspace(100, 200, 210)))    # por encima de su SMA200
    down = _series(list(np.linspace(200, 100, 210)))  # por debajo
    assert trend_bull({"BTC/USDT": up}, "BTC/USDT", 200) is True
    assert trend_bull({"BTC/USDT": down}, "BTC/USDT", 200) is False


def test_select_targets_cash_in_bear():
    cfg = XSMomConfig(lookback_days=30, top_k=2, trend_filter=True,
                      trend_symbol="BTC/USDT", trend_sma=200)
    down = _series(list(np.linspace(200, 100, 210)))
    closes = {"BTC/USDT": down, "A/USDT": _series([100] * 40 + [130]),
              "B/USDT": _series([100] * 40 + [120])}
    assert select_targets(closes, cfg) == []          # BTC bajo SMA200 -> cash


def test_select_targets_topk_in_bull():
    cfg = XSMomConfig(lookback_days=30, top_k=2, trend_filter=True,
                      trend_symbol="BTC/USDT", trend_sma=200)
    up = _series(list(np.linspace(100, 200, 210)))
    closes = {"BTC/USDT": up,
              "A/USDT": _series([100] * 180 + list(np.linspace(100, 150, 30))),
              "B/USDT": _series([100] * 180 + list(np.linspace(100, 130, 30))),
              "C/USDT": _series([100] * 180 + list(np.linspace(100, 110, 30)))}
    tg = select_targets(closes, cfg)
    assert set(tg) == {"A/USDT", "B/USDT"}            # los 2 de mayor momentum


def test_portfolio_rebalance_and_equity():
    pf = XSMomPortfolio(starting_balance=1000, fee_pct=0.001)
    prices = {"A/USDT": 10.0, "B/USDT": 20.0}
    fee = pf.rebalance(["A/USDT", "B/USDT"], prices)
    # invierte todo equal-weight: ~500 en cada uno menos comisión
    assert abs(fee - 1000 * 0.001) < 1e-6            # turnover = 1000 (todo entra)
    assert pf.cash == 0.0
    assert abs(pf.equity(prices) - (1000 - fee)) < 1e-6
    # sube A un 20% -> equity sube ~la mitad de ese 20%
    eq2 = pf.equity({"A/USDT": 12.0, "B/USDT": 20.0})
    assert eq2 > pf.equity(prices)


def test_portfolio_cash_when_no_targets():
    pf = XSMomPortfolio(starting_balance=1000, fee_pct=0.001)
    pf.rebalance(["A/USDT"], {"A/USDT": 10.0})
    eq_before = pf.equity({"A/USDT": 10.0})
    pf.rebalance([], {"A/USDT": 10.0})               # a cash
    assert pf.holdings == {}
    assert abs(pf.cash - eq_before + eq_before * 0.001) < 1e-3   # paga comisión al salir


def test_runner_not_started_when_disabled():
    cfg = make_config(make_instrument())
    cfg.xsmom.enabled = False
    assert daemon._maybe_start_xsmom(cfg, NullNotifier()) is None


UNIV3 = ["A/USDT", "B/USDT", "C/USDT"]
PRICES = {"A/USDT": 10.0, "B/USDT": 10.0, "C/USDT": 10.0}


def test_live_rebalance_from_cash_buys_targets():
    cfg = make_config(make_instrument(), starting_balance=100)
    ex = _FakeExLive({"USDT": 100.0})
    ex_ = LiveXSMomExecutor(cfg, ex, UNIV3, dry_run=False)
    ex_.rebalance(["A/USDT", "B/USDT"], PRICES)      # equity 100, per 50
    assert ex.sells == []
    assert {s for s, _ in ex.buys} == {"A/USDT", "B/USDT"}
    assert all(abs(c - 50.0) < 1e-6 for _, c in ex.buys)


def test_live_rebalance_rotates_out_of_c_into_b():
    cfg = make_config(make_instrument(), starting_balance=100)
    ex = _FakeExLive({"USDT": 10.0, "A": 5.0, "C": 3.0})   # A=50, C=30, cash=10 -> eq 90, per 45
    ex_ = LiveXSMomExecutor(cfg, ex, UNIV3, dry_run=False)
    ex_.rebalance(["A/USDT", "B/USDT"], PRICES)
    sold = {s for s, _ in ex.sells}
    bought = {s for s, _ in ex.buys}
    assert "C/USDT" in sold                     # C fuera del top -> vendida
    assert "B/USDT" in bought                    # B entra -> comprada
    assert "B/USDT" not in sold


def test_live_dry_run_sends_nothing():
    cfg = make_config(make_instrument(), starting_balance=100)
    ex = _FakeExLive({"USDT": 100.0})
    LiveXSMomExecutor(cfg, ex, UNIV3, dry_run=True).rebalance(["A/USDT"], PRICES)
    assert ex.buys == [] and ex.sells == []


def test_runner_selects_paper_vs_live(monkeypatch):
    monkeypatch.delenv(XSMOM_LIVE_CONFIRM_ENV, raising=False)
    cfg = make_config(make_instrument(), starting_balance=100)
    cfg.xsmom.universe = UNIV3
    assert isinstance(XSMomRunner(cfg, object(), NullNotifier()).pf, XSMomPortfolio)  # paper

    cfg.mode = "live"
    r = XSMomRunner(cfg, object(), NullNotifier())
    assert isinstance(r.pf, LiveXSMomExecutor) and r.pf.dry_run is True   # sin confirmación

    monkeypatch.setenv(XSMOM_LIVE_CONFIRM_ENV, XSMOM_LIVE_CONFIRM)
    r2 = XSMomRunner(cfg, object(), NullNotifier())
    assert isinstance(r2.pf, LiveXSMomExecutor) and r2.pf.dry_run is False  # confirmado
