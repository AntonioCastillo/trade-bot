"""Ejecutor real del carry: sizing, dry-run, deshacer spot si falla el corto,
selección paper/real en el runner y cierre de emergencia por liquidación.

Todo con DOBLES: no toca red ni envía órdenes."""

from conftest import make_config, make_instrument

from tradebot.carry import CARRY_LIVE_CONFIRM, CARRY_LIVE_CONFIRM_ENV, CarryManager, CarryRunner
from tradebot.carry_live import LiveCarryExecutor
from tradebot.notifier import NullNotifier


class FakeSpot:
    def __init__(self, free=1000.0, price=2000.0):
        self.free = free
        self.price = price
        self.buys = []
        self.sells = []

    def fetch_balance(self, cur):
        return self.free

    def fetch_last_price(self, sym):
        return self.price

    def create_market_buy(self, sym, cost):
        self.buys.append((sym, cost))
        return {"average": self.price, "filled": cost / self.price, "fee": {"cost": 0.0}}

    def create_market_sell(self, sym, amount):
        self.sells.append((sym, amount))
        return {"average": self.price, "filled": amount, "fee": {"cost": 0.0}}


class FakeBroker:
    def __init__(self, dry_run=True, leverage=1.0, contract_size=0.01, free=1000.0,
                 fail_short=False, position=None):
        self.dry_run = dry_run
        self.leverage = leverage
        self._cs = contract_size
        self.free = free
        self.fail_short = fail_short
        self.position = position
        self.shorts = []
        self.closes = []

    def contract_size(self, sym):
        return self._cs

    def contracts_for_notional(self, sym, notional, price):
        return float(int(notional / (price * self._cs)))

    def notional_of(self, sym, contracts, price):
        return contracts * self._cs * price

    def fetch_free_usdt(self):
        return self.free

    def open_short(self, sym, contracts, price):
        if self.fail_short:
            raise RuntimeError("perp rechazado")
        self.shorts.append((sym, contracts))
        return {"average": price, "filled": contracts, "fee": {"cost": 0.0}}

    def close_short(self, sym, contracts, price):
        self.closes.append((sym, contracts))
        return {"average": price, "filled": contracts, "fee": {"cost": 0.0}}

    def fetch_position(self, sym):
        return self.position


def _cfg():
    cfg = make_config(make_instrument())
    cfg.carry.max_notional_usdt = 50.0
    cfg.carry.notional_pct = 0.20
    cfg.carry.leverage = 1.0
    return cfg


def test_dryrun_open_no_real_spot_order():
    cfg = _cfg()
    spot, broker = FakeSpot(), FakeBroker(dry_run=True)
    ex = LiveCarryExecutor(cfg, spot, broker, NullNotifier())
    pos = ex.open("ETH/USDT", spot_price=2000.0, perp_price=2000.0)
    assert pos is not None and "ETH/USDT" in ex.positions
    assert spot.buys == []                 # dry-run: NO compra spot real
    assert broker.shorts                    # sí registra el corto (el broker lo simula)
    # notional topado a 50 -> spot_amount = 50/2000
    assert abs(pos.spot_amount - 50 / 2000) < 1e-9


def test_notional_capped_by_max():
    cfg = _cfg()
    cfg.carry.max_notional_usdt = 20.0     # tope más bajo que el 20% de 1000
    spot, broker = FakeSpot(free=1000.0), FakeBroker(dry_run=False, free=1000.0)
    ex = LiveCarryExecutor(cfg, spot, broker, NullNotifier())
    ex.open("ETH/USDT", spot_price=2000.0, perp_price=2000.0)
    sym, cost = spot.buys[0]
    assert cost == 20.0                     # respeta el tope duro


def test_perp_failure_unwinds_spot():
    cfg = _cfg()
    spot = FakeSpot(free=1000.0)
    broker = FakeBroker(dry_run=False, free=1000.0, fail_short=True)
    ex = LiveCarryExecutor(cfg, spot, broker, NullNotifier())
    pos = ex.open("ETH/USDT", spot_price=2000.0, perp_price=2000.0)
    assert pos is None
    assert "ETH/USDT" not in ex.positions
    assert spot.buys and spot.sells         # compró y DESHIZO el spot
    assert spot.sells[0][0] == "ETH/USDT"


def test_runner_uses_paper_in_paper_mode():
    cfg = _cfg()               # mode=paper por defecto -> todo paper
    runner = CarryRunner(cfg, exchange=object(), notifier=NullNotifier())
    assert isinstance(runner.mgr, CarryManager)


def test_runner_live_dryrun_without_confirm(monkeypatch):
    monkeypatch.delenv(CARRY_LIVE_CONFIRM_ENV, raising=False)
    cfg = _cfg()
    cfg.mode = "live"          # live -> el carry va REAL (sin flag extra)
    cfg.credentials.api_key = "k"
    cfg.credentials.api_secret = "s"
    cfg.credentials.api_passphrase = "p"
    runner = CarryRunner(cfg, exchange=object(), notifier=NullNotifier())
    assert isinstance(runner.mgr, LiveCarryExecutor)
    assert runner.mgr.dry_run is True       # 1ª vez sin confirmación -> dry-run (no paper)


def test_runner_live_real_with_confirm(monkeypatch):
    monkeypatch.setenv(CARRY_LIVE_CONFIRM_ENV, CARRY_LIVE_CONFIRM)
    cfg = _cfg()
    cfg.mode = "live"
    cfg.credentials.api_key = "k"
    cfg.credentials.api_secret = "s"
    cfg.credentials.api_passphrase = "p"
    runner = CarryRunner(cfg, exchange=object(), notifier=NullNotifier())
    assert isinstance(runner.mgr, LiveCarryExecutor)
    assert runner.mgr.dry_run is False      # confirmado -> ejecuta de verdad


def test_monitor_emergency_close_near_liquidation():
    cfg = _cfg()
    spot = FakeSpot(free=1000.0, price=2100.0)
    # Corto cuya liquidación (2200) está a solo ~4.8% del precio de marca (2100)
    broker = FakeBroker(dry_run=False, free=1000.0,
                        position={"contracts": 2.0, "side": "short", "entry_price": 2000.0,
                                  "mark_price": 2100.0, "liquidation_price": 2200.0,
                                  "unrealized_pnl": 0.0, "collateral": 40.0})
    ex = LiveCarryExecutor(cfg, spot, broker, NullNotifier())
    ex.open("ETH/USDT", spot_price=2000.0, perp_price=2000.0)  # crea la posición
    ex.monitor()
    assert "ETH/USDT" not in ex.positions   # cerrada de emergencia
    assert spot.sells and broker.closes
