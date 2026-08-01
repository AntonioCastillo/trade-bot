from conftest import make_config, make_instrument

from tradebot.sniper import Sniper, detect_new_listings


def test_detect_new_listings_filters_by_quote():
    known = {"BTC/USDT", "ETH/USDT"}
    current = {"BTC/USDT", "ETH/USDT", "NEW/USDT", "FOO/BTC"}
    assert detect_new_listings(current, known, "USDT") == ["NEW/USDT"]  # FOO/BTC fuera


def test_no_new_listings():
    s = {"BTC/USDT", "ETH/USDT"}
    assert detect_new_listings(s, s, "USDT") == []


class _FakeExchange:
    """Exchange falso controlable para tests (sin red)."""

    def __init__(self, symbols, price):
        self._symbols = set(symbols)
        self._price = price

    def market_symbols(self):
        return set(self._symbols)

    def fetch_last_price(self, symbol):
        return self._price

    def set_price(self, p):
        self._price = p

    def add_symbol(self, s):
        self._symbols.add(s)


def _sniper(tmp_path, exchange):
    ins = make_instrument()
    config = make_config(ins, starting_balance=1_000)
    config.sniper.baseline_path = str(tmp_path / "known.json")
    config.sniper.position_size_pct = 0.02
    config.sniper.take_profit_pct = 0.5
    config.sniper.stop_loss_pct = 0.15
    return Sniper(config, exchange, live=False)


def test_bootstrap_then_detect_new(tmp_path):
    ex = _FakeExchange(["BTC/USDT", "ETH/USDT"], price=1.0)
    sniper = _sniper(tmp_path, ex)
    sniper.bootstrap()
    assert sniper.poll() == []          # nada nuevo aún
    ex.add_symbol("MOON/USDT")
    assert sniper.poll() == ["MOON/USDT"]


def test_paper_enter_reduces_balance_and_sets_targets(tmp_path):
    ex = _FakeExchange(["BTC/USDT"], price=2.0)
    sniper = _sniper(tmp_path, ex)
    sniper.bootstrap()
    sniper.enter("MOON/USDT")

    assert len(sniper.snipes) == 1
    snipe = sniper.snipes[0]
    assert snipe.entry_price == 2.0
    assert snipe.take_profit == 3.0     # +50%
    assert snipe.stop_loss == 1.7       # -15%
    # 2% de 1000 = 20 gastados.
    assert sniper._paper_balance == 980.0


def test_paper_exit_on_take_profit(tmp_path):
    ex = _FakeExchange(["BTC/USDT"], price=2.0)
    sniper = _sniper(tmp_path, ex)
    sniper.bootstrap()
    sniper.enter("MOON/USDT")

    ex.set_price(3.5)                    # por encima del TP (3.0)
    sniper.manage()
    assert sniper.snipes == []           # cerrado
    assert sniper._paper_balance > 1_000  # ganancia realizada
