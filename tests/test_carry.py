import pytest

from tradebot.carry import CarryManager, annualized_pct
from tradebot.config import CarryConfig


def _mgr(**kw):
    cfg = CarryConfig(notional_pct=0.20, min_annualized_pct=5.0,
                      exit_annualized_pct=0.0, fee_pct=0.0008)
    for k, v in kw.items():
        setattr(cfg, k, v)
    return CarryManager(cfg, starting_balance=1000.0)


def test_annualized():
    # 0.01% por periodo * 1095 periodos = 10.95%
    assert annualized_pct(0.0001) == pytest.approx(0.0001 * 1095 * 100)


def test_should_open_only_above_threshold():
    m = _mgr()
    # 0.0001/periodo -> ~10.95% anualizado > 5% -> abrir
    assert m.should_open("ETH/USDT", 0.0001) is True
    # 0.00001/periodo -> ~1.1% < 5% -> no abrir
    assert m.should_open("ETH/USDT", 0.00001) is False


def test_open_deducts_notional_and_fees():
    m = _mgr()
    m.open("ETH/USDT", spot_price=2000.0, perp_price=2000.0)
    pos = m.positions["ETH/USDT"]
    assert pos.notional == pytest.approx(200.0)          # 20% de 1000
    assert pos.spot_amount == pytest.approx(0.1)         # 200 / 2000
    # balance = 1000 - 200 (spot) - 200*0.0008*2 (fees) = 799.68
    assert m.balance == pytest.approx(1000 - 200 - 200 * 0.0008 * 2)


def test_delta_neutral_offsets_price_moves():
    m = _mgr()
    m.open("ETH/USDT", 2000.0, 2000.0)
    # Sube un 10% spot y perp por igual -> spot gana, corto pierde -> equity ~ igual.
    eq0 = m.equity({"ETH/USDT": (2000.0, 2000.0)})
    eq1 = m.equity({"ETH/USDT": (2200.0, 2200.0)})
    assert eq1 == pytest.approx(eq0, abs=1e-6)


def test_funding_accrues_and_grows_equity():
    m = _mgr()
    m.open("ETH/USDT", 2000.0, 2000.0, funding_ts=1000)
    pay = m.accrue_funding("ETH/USDT", rate=0.0001, funding_ts=2000)
    assert pay == pytest.approx(0.0001 * 200)            # funding sobre el notional
    # No re-acumula el mismo/antiguo timestamp.
    assert m.accrue_funding("ETH/USDT", rate=0.0001, funding_ts=2000) == 0.0


def test_close_realizes_into_balance():
    m = _mgr()
    m.open("ETH/USDT", 2000.0, 2000.0)
    b_before = m.balance
    net = m.close("ETH/USDT", 2000.0, 2000.0)   # precios planos
    assert "ETH/USDT" not in m.positions
    # Sin cambio de precio ni funding: pérdida = comisiones de cierre.
    assert net == pytest.approx(-200 * 0.0008 * 2)
