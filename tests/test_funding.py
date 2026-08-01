from tradebot.funding import PERIODS_PER_YEAR, analyze_funding


def test_empty_funding():
    r = analyze_funding("BTC/USDT:USDT", [])
    assert r.periods == 0 and r.annualized_pct == 0.0


def test_annualized_and_positive():
    # Funding constante 0.0001 (0.01%) por periodo, todos positivos.
    rates = [0.0001] * 30
    r = analyze_funding("BTC/USDT:USDT", rates)
    assert r.periods == 30
    assert r.positive_pct == 100.0
    assert r.annualized_pct == 0.0001 * PERIODS_PER_YEAR * 100
    assert abs(r.cumulative_pct - 0.0001 * 30 * 100) < 1e-9


def test_mixed_signs_positive_pct():
    rates = [0.001, -0.001, 0.001, 0.001]   # 3 de 4 positivos
    r = analyze_funding("X", rates)
    assert r.positive_pct == 75.0
    assert abs(r.cumulative_pct - (0.002 * 100)) < 1e-9   # suma neta 0.002
