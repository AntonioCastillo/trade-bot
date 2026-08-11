"""Simulación del carry con umbral de funding (histéresis entrada/salida)."""

from tradebot.funding import simulate_threshold_carry


def test_threshold_gates_entry_and_exit():
    # 5 periodos de funding alto (0.001 = 109.5% anual), luego 3 bajos
    # (0.00005 = 5.5% anual). Sin basis (spot=perp constantes).
    funding = [0.001] * 5 + [0.00005] * 3
    spot = [100.0] * 8
    perp = [100.0] * 8
    sim = simulate_threshold_carry("X", funding, spot, perp,
                                   entry_pct=50, exit_pct=25, roundtrip_cost_pct=0.32)
    # Entra en el 1er periodo (109.5≥50), sigue mientras ≥25; el 6º (5.5<25) se
    # cobra y sale -> 6 periodos dentro, 1 solo viaje.
    assert sim.trips == 1
    assert sim.periods_in == 6
    # funding cobrado = 5×0.001 + 1×0.00005 = 0.00505 -> 0.505%
    assert abs(sim.funding_pct - 0.505) < 1e-6
    assert abs(sim.basis_pct) < 1e-9
    # neto = funding - coste
    assert abs(sim.net_pct - (0.505 - 0.32)) < 1e-6


def test_high_threshold_never_enters():
    funding = [0.0001] * 10   # ~11% anual, por debajo del umbral
    sim = simulate_threshold_carry("X", funding, [1.0] * 10, [1.0] * 10,
                                   entry_pct=200, exit_pct=100)
    assert sim.trips == 0 and sim.periods_in == 0
    assert sim.net_pct == 0.0


def test_always_in_when_threshold_zero():
    funding = [0.0002] * 9   # todos positivos
    sim = simulate_threshold_carry("X", funding, [1.0] * 9, [1.0] * 9,
                                   entry_pct=0, exit_pct=-1000)
    assert sim.periods_in == 9 and sim.trips == 1
