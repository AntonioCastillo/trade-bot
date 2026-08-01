import pytest

from tradebot.selfcheck import run_api_check


class _FakeExchange:
    """Simula respuestas de ccxt para una compra y venta a mercado."""

    def __init__(self, buy_price=2.0, sell_price=1.98):
        self.buy_price = buy_price
        self.sell_price = sell_price
        self.calls = []
        self._bought = 0.0

    def create_market_buy(self, symbol, cost):
        self.calls.append(("buy", symbol, cost))
        amount = cost / self.buy_price
        self._bought = amount
        return {"filled": amount, "average": self.buy_price, "cost": cost}

    def fetch_balance(self, currency):
        return self._bought

    def create_market_sell(self, symbol, amount):
        self.calls.append(("sell", symbol, amount))
        return {"filled": amount, "average": self.sell_price,
                "cost": amount * self.sell_price}


def test_api_check_roundtrip_computes_net():
    ex = _FakeExchange(buy_price=2.0, sell_price=1.98)
    r = run_api_check(ex, "BTC/USDT", usd=1.0)

    assert r.amount == pytest.approx(0.5)          # 1 USD / 2.0
    assert r.cost == pytest.approx(1.0)
    assert r.proceeds == pytest.approx(0.99)        # 0.5 * 1.98
    assert r.net == pytest.approx(-0.01)            # coste de la validación
    # Debe comprar y luego vender la cantidad exacta comprada.
    assert ex.calls[0][0] == "buy"
    assert ex.calls[1] == ("sell", "BTC/USDT", pytest.approx(0.5))


def test_api_check_raises_if_no_fill():
    class _NoFill(_FakeExchange):
        def create_market_buy(self, symbol, cost):
            return {"filled": 0, "cost": cost}

    with pytest.raises(RuntimeError):
        run_api_check(_NoFill(), "BTC/USDT", usd=1.0)
