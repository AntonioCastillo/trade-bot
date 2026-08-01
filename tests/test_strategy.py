from tradebot.models import SignalType
from tradebot.strategy.mean_reversion import MeanReversionStrategy


def test_hold_when_not_enough_candles(price_series):
    strat = MeanReversionStrategy(rsi_period=14, bb_period=20)
    candles = price_series([100.0] * 5)
    sig = strat.generate_signal("BTC/USDT", candles)
    assert sig.type is SignalType.HOLD


def test_buy_signal_on_oversold_crash(price_series):
    # Precio estable y luego una caída brusca -> sobreventa (RSI bajo + banda inf).
    prices = [100.0] * 25 + [95, 90, 85, 80, 70]
    strat = MeanReversionStrategy(
        rsi_period=14, rsi_oversold=35, bb_period=20, bb_std=2.0
    )
    sig = strat.generate_signal("BTC/USDT", price_series(prices))
    assert sig.type is SignalType.BUY


def test_no_short_on_overbought_spike(price_series):
    # Solo-largos (spot): en sobrecompra NO abre corto -> HOLD.
    prices = [100.0] * 25 + [105, 110, 115, 120, 130]
    strat = MeanReversionStrategy(
        rsi_period=14, rsi_overbought=65, bb_period=20, bb_std=2.0
    )
    sig = strat.generate_signal("BTC/USDT", price_series(prices))
    assert sig.type is SignalType.HOLD


def test_hold_when_price_in_range(price_series):
    # Ruido pequeño alrededor de la media -> sin señal.
    prices = [100.0 + (i % 3 - 1) * 0.5 for i in range(50)]
    strat = MeanReversionStrategy()
    sig = strat.generate_signal("BTC/USDT", price_series(prices))
    assert sig.type is SignalType.HOLD
