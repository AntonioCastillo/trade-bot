from conftest import make_config, make_instrument

from tradebot.backtester import run_backtest
from tradebot.metrics import compute_metrics
from tradebot.strategy.mean_reversion import MeanReversionStrategy


def test_backtest_produces_closed_trade(price_series):
    ins = make_instrument(symbol="BTC/USDT", strategy_name="mean_reversion",
                          stop_loss_pct=0.03, take_profit_pct=0.06)
    config = make_config(ins, starting_balance=10_000)
    strategy = MeanReversionStrategy(rsi_period=14, rsi_oversold=35, bb_period=20, bb_std=2.0)

    # Caída (abre por sobreventa) y recuperación por encima del take-profit.
    prices = [100.0] * 25 + [95, 90, 85, 80, 70, 78]
    result = run_backtest(price_series(prices), strategy, ins, config)

    assert len(result.trades) >= 1
    m = compute_metrics(result.trades, result.starting_balance)
    assert m.trades == len(result.trades)


def test_backtest_no_trades_is_empty(price_series):
    ins = make_instrument(symbol="BTC/USDT")
    config = make_config(ins)
    strategy = MeanReversionStrategy()
    prices = [100.0 + (i % 3 - 1) * 0.2 for i in range(60)]  # ruido plano
    result = run_backtest(price_series(prices), strategy, ins, config)
    assert result.trades == []
