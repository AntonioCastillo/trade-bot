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


def _lottery_sniper(tmp_path, exchange):
    """Sniper en modo billete: TP x100, sin SL, sin timeout."""
    ins = make_instrument()
    config = make_config(ins, starting_balance=1_000)
    config.sniper.baseline_path = str(tmp_path / "known.json")
    config.sniper.position_size_pct = 0.01
    config.sniper.take_profit_pct = 99.0      # x100
    config.sniper.stop_loss_pct = 0.0         # sin stop
    config.sniper.timeout_minutes = 0         # sin timeout
    return Sniper(config, exchange, live=False)


def test_lottery_mode_disables_sl_and_timeout(tmp_path):
    ex = _FakeExchange(["BTC/USDT"], price=1.0)
    sniper = _lottery_sniper(tmp_path, ex)
    sniper.bootstrap()
    sniper.enter("MOON/USDT")
    snipe = sniper.snipes[0]
    assert snipe.stop_loss == 0.0             # sin stop
    assert snipe.deadline is None             # sin timeout
    assert snipe.take_profit == 100.0         # x100 desde 1.0

    # Se desploma un 90%: NO debe cerrar (se aguanta el billete).
    ex.set_price(0.1)
    sniper.manage()
    assert len(sniper.snipes) == 1

    # Llega al x100: cierra por take-profit.
    ex.set_price(100.0)
    sniper.manage()
    assert sniper.snipes == []


class _NoPriceThenPrice:
    """Recién listada: la 1ª lectura de precio falla (sin trades), la 2ª ya da precio."""
    def __init__(self):
        self.calls = 0

    def market_symbols(self):
        return {"MOON/USDT"}

    def fetch_last_price(self, symbol):
        self.calls += 1
        if self.calls == 1:
            raise ValueError("sin precio todavía")
        return 2.0


def test_enter_retries_when_no_price_yet(tmp_path):
    ex = _NoPriceThenPrice()
    sniper = _sniper(tmp_path, ex)
    assert sniper.enter("MOON/USDT") is False   # aún sin precio -> reintentar
    assert sniper.snipes == []
    assert sniper.enter("MOON/USDT") is True     # ahora sí entra
    assert len(sniper.snipes) == 1


def test_fetch_last_price_fallback_and_clean_error():
    from tradebot.exchange import Exchange
    import pytest as _pytest
    cfg = make_config(make_instrument())
    ex = Exchange(cfg)

    class _Client:
        def __init__(self, ticker):
            self.ticker = ticker

        def fetch_ticker(self, symbol):
            return self.ticker

    ex._client = _Client({"last": None, "close": 5.0, "bid": None, "ask": None})
    assert ex.fetch_last_price("X/USDT") == 5.0          # cae a 'close'
    ex._client = _Client({"last": None, "close": None, "bid": None, "ask": None})
    with _pytest.raises(ValueError):                     # sin precio -> error limpio
        ex.fetch_last_price("X/USDT")


def test_sniper_persists_and_reloads_snipes(tmp_path):
    ex = _FakeExchange(["BTC/USDT"], price=2.0)
    s1 = _lottery_sniper(tmp_path, ex)
    s1.snipes_path = str(tmp_path / "snipes.json")
    s1.bootstrap()
    s1.enter("MOON/USDT")
    s1._save_snipes()
    bal = s1._paper_balance

    # Reinicio: nueva instancia recarga los billetes y el efectivo.
    s2 = _lottery_sniper(tmp_path, ex)
    s2.snipes_path = str(tmp_path / "snipes.json")
    s2._load_snipes()
    assert len(s2.snipes) == 1
    assert s2.snipes[0].symbol == "MOON/USDT"
    assert s2.snipes[0].deadline is None          # modo lotería: sin timeout, se preserva
    assert abs(s2._paper_balance - bal) < 1e-9


def test_summary_marks_open_tickets(tmp_path):
    ex = _FakeExchange(["BTC/USDT"], price=1.0)
    sniper = _lottery_sniper(tmp_path, ex)
    sniper.bootstrap()
    sniper.enter("MOON/USDT")             # invierte 1% de 1000 = 10
    ex.set_price(0.5)                     # el billete cae a la mitad
    s = sniper.summary()
    assert s["open"] == 1
    assert abs(s["invested"] - 10.0) < 1e-9
    assert abs(s["value"] - 5.0) < 1e-9   # 10 -> 5
    assert s["pnl"] < 0
