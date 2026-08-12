"""Persistencia y readopción de posiciones abiertas (reinicio seguro)."""

import numpy as np
import pandas as pd
from conftest import make_config, make_instrument

from tradebot.engine import Engine
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.models import Position, Side, Signal, SignalType
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy.base import Strategy


def _df(prices):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="1h", tz="UTC")
    close = pd.Series(prices, index=idx)
    return pd.DataFrame({"open": close, "high": close * 1.001, "low": close * 0.999,
                         "close": close, "volume": np.full(len(prices), 100.0)})


class _BuyOnce(Strategy):
    min_candles = 1

    def __init__(self):
        self.done = False

    def generate_signal(self, symbol, candles):
        price = float(candles["close"].iloc[-1])
        if self.done:
            return Signal(SignalType.HOLD, symbol, price)
        self.done = True
        return Signal(SignalType.BUY, symbol, price, "test")


class _Hold(Strategy):
    min_candles = 1

    def generate_signal(self, symbol, candles):
        return Signal(SignalType.HOLD, symbol, float(candles["close"].iloc[-1]))


def test_storage_open_position_roundtrip(tmp_path):
    st = Storage(str(tmp_path / "t.db"))
    pos = Position(symbol="BTC/USDT", side=Side.BUY, amount=0.5, entry_price=100.0,
                   stop_loss=90.0, take_profit=130.0, category="trend1d",
                   strategy_name="trend", entry_fee=0.1, reason="x",
                   trailing_stop_pct=0.1, peak_price=100.0, bars_held=2)
    st.save_open_position(pos)
    assert pos.db_id > 0

    loaded = st.load_open_positions()
    assert len(loaded) == 1
    assert loaded[0].symbol == "BTC/USDT" and loaded[0].bars_held == 2
    assert loaded[0].db_id == pos.db_id

    pos.stop_loss, pos.peak_price, pos.bars_held = 95.0, 120.0, 5
    st.update_open_position(pos)
    l2 = st.load_open_positions()[0]
    assert l2.stop_loss == 95.0 and l2.peak_price == 120.0 and l2.bars_held == 5

    st.delete_open_position(pos)
    assert st.load_open_positions() == []
    st.close()


def test_state_key_value(tmp_path):
    st = Storage(str(tmp_path / "s.db"))
    assert st.get_state("paper_balance", 0.0) == 0.0
    st.set_state("paper_balance", 987.5)
    assert st.get_state("paper_balance") == 987.5
    st.close()


def _engine(cfg, storage):
    return Engine(cfg, {"BTC/USDT": _BuyOnce()}, RiskManager(cfg.risk),
                  PaperExecutionEngine(cfg), storage, enforce_daily_loss=False)


def test_engine_persists_and_readopts(tmp_path):
    db = str(tmp_path / "e.db")
    ins = make_instrument(symbol="BTC/USDT", category="trend1d", strategy_name="trend",
                          stop_loss_pct=0.10, take_profit_pct=0.50)
    cfg = make_config(ins, starting_balance=1000)
    df = _df([100.0] * 30)

    st1 = Storage(db)
    eng1 = _engine(cfg, st1)
    eng1.process("BTC/USDT", df)
    assert len(eng1.positions) == 1
    cash_after = eng1.execution.get_balance()
    assert st1.get_state("paper_balance") == cash_after     # efectivo persistido
    st1.close()

    # Reinicio: nueva conexión al MISMO fichero + nuevo engine que readopta.
    st2 = Storage(db)
    eng2 = _engine(cfg, st2)
    assert eng2.positions == []                              # aún no ha readoptado
    n = eng2.load_positions()
    assert n == 1
    assert eng2.positions[0].symbol == "BTC/USDT"
    assert abs(eng2.execution.get_balance() - cash_after) < 1e-6   # efectivo restaurado
    st2.close()


class _FakeEx:
    """Exchange falso que solo expone los saldos totales (para reconciliar)."""
    def __init__(self, balances):
        self._b = balances

    def fetch_balances_total(self):
        return dict(self._b)


def _pos(symbol, amount, category, strategy):
    return Position(symbol=symbol, side=Side.BUY, amount=amount, entry_price=100.0,
                    stop_loss=90.0, take_profit=130.0, category=category, strategy_name=strategy)


def test_reconcile_live_drops_adjusts_keeps(tmp_path):
    db = str(tmp_path / "r.db")
    cfg = make_config(make_instrument(symbol="BTC/USDT"), starting_balance=1000)
    cfg.mode = "live"

    st = Storage(db)
    for p in (_pos("BTC/USDT", 1.0, "trend1d", "trend"),      # real 1.0 -> KEEP
              _pos("ETH/USDT", 2.0, "momentum1d", "momentum"),  # real 0   -> DROP
              _pos("SOL/USDT", 4.0, "breakout1d", "breakout")): # real 3.0 -> SHRINK
        st.save_open_position(p)

    fake = _FakeEx({"BTC": 1.0, "SOL": 3.0})   # ETH ausente = 0
    eng = Engine(cfg, {}, RiskManager(cfg.risk), PaperExecutionEngine(cfg), st,
                 exchange=fake, enforce_daily_loss=False)
    n = eng.load_positions()

    assert n == 2
    by_sym = {p.symbol: p for p in eng.positions}
    assert set(by_sym) == {"BTC/USDT", "SOL/USDT"}      # ETH descartada
    assert by_sym["BTC/USDT"].amount == 1.0             # intacta
    assert by_sym["SOL/USDT"].amount == 3.0             # ajustada al saldo real

    # Persistido: ETH borrada, SOL ajustada en la BD.
    persisted = {p.symbol: p.amount for p in st.load_open_positions()}
    assert persisted == {"BTC/USDT": 1.0, "SOL/USDT": 3.0}
    st.close()


def test_reconcile_skipped_in_paper(tmp_path):
    """En paper NO se reconcilia (no hay saldo real que comprobar)."""
    db = str(tmp_path / "p.db")
    cfg = make_config(make_instrument(symbol="BTC/USDT"), starting_balance=1000)  # mode=paper
    st = Storage(db)
    st.save_open_position(_pos("BTC/USDT", 1.0, "trend1d", "trend"))
    fake = _FakeEx({})   # sin saldos: en live descartaría; en paper NO debe tocarse
    eng = Engine(cfg, {}, RiskManager(cfg.risk), PaperExecutionEngine(cfg), st,
                 exchange=fake, enforce_daily_loss=False)
    assert eng.load_positions() == 1
    st.close()


def test_readopted_position_still_managed(tmp_path):
    """Tras readoptar, el motor sigue gestionando la salida (SL) y la borra al cerrar."""
    db = str(tmp_path / "m.db")
    ins = make_instrument(symbol="BTC/USDT", category="trend1d", strategy_name="trend",
                          stop_loss_pct=0.10, take_profit_pct=0.50)
    cfg = make_config(ins, starting_balance=1000)

    st1 = Storage(db)
    eng1 = _engine(cfg, st1)
    eng1.process("BTC/USDT", _df([100.0] * 30))
    st1.close()

    st2 = Storage(db)
    # Estrategia HOLD para aislar la SALIDA (que no reentre tras cerrar).
    eng2 = Engine(cfg, {"BTC/USDT": _Hold()}, RiskManager(cfg.risk),
                  PaperExecutionEngine(cfg), st2, enforce_daily_loss=False)
    eng2.load_positions()
    assert len(eng2.positions) == 1
    # Precio se desploma por debajo del stop (90) -> debe cerrar y borrar la fila.
    eng2.process("BTC/USDT", _df([100.0] * 29 + [80.0]))
    assert eng2.positions == []
    assert st2.load_open_positions() == []
    st2.close()
