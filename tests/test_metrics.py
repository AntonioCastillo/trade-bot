import math

import pytest

from tradebot.metrics import compute_metrics, metrics_from_pnls


class _T:
    def __init__(self, pnl_abs, pnl_pct):
        self.pnl_abs = pnl_abs
        self.pnl_pct = pnl_pct


def test_empty_metrics_are_zero():
    m = metrics_from_pnls([], [], 10_000)
    assert m.trades == 0
    assert m.total_pnl == 0
    assert m.max_drawdown_pct == 0


def test_basic_metrics():
    m = metrics_from_pnls([10, -4, 6], [10, -4, 6], 10_000)
    assert m.trades == 3
    assert m.wins == 2
    assert m.win_rate == pytest.approx(2 / 3)
    assert m.total_pnl == 12
    assert m.profit_factor == pytest.approx(16 / 4)  # gains 16 / losses 4
    assert m.max_drawdown_pct > 0
    assert m.sharpe == pytest.approx(4 / 5.887840577, rel=1e-3)


def test_profit_factor_infinite_without_losses():
    m = metrics_from_pnls([5, 3, 2], [5, 3, 2], 10_000)
    assert math.isinf(m.profit_factor)


def test_max_drawdown_captures_peak_to_trough():
    # +100, -60, -60 -> pico 10.100, valle 9.980 -> DD = 120/10100
    m = metrics_from_pnls([100, -60, -60], [1, -0.6, -0.6], 10_000)
    assert m.max_drawdown_pct == pytest.approx(120 / 10_100 * 100, rel=1e-6)


def test_compute_metrics_from_objects():
    trades = [_T(10, 1.0), _T(-5, -0.5)]
    m = compute_metrics(trades, 1_000)
    assert m.trades == 2
    assert m.total_pnl == 5
