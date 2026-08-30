"""Backtest de volume_surge sobre ETH, SOL, BNB, AVAX en 4h (últimos 3 meses)."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.config import Instrument, RiskConfig, load_config
from tradebot.engine import Engine
from tradebot.exchange import Exchange
from tradebot.execution.paper import PaperExecutionEngine
from tradebot.risk import RiskManager
from tradebot.storage import Storage
from tradebot.strategy import build_strategy
from tradebot.reporting import render_report

DB_PATH = "data/backtest_volsurge.db"

SYMBOLS = ["ETH/USDT", "SOL/USDT", "BNB/USDT", "AVAX/USDT"]
TIMEFRAME = "4h"
# 3 meses de velas 4h ≈ 90 * 6 = 540 velas
LIMIT = 550

STRATEGY_PARAMS = {
    "vol_period": 20,
    "surge_mult": 2.5,
    "min_change_pct": 0.01,
}

RISK_OVERRIDES = {
    "stop_loss_pct": 0.06,
    "take_profit_pct": 0.20,
    "trailing_stop_pct": 0.08,
    "partial_take_profit_pct": 0.05,
}


def main() -> None:
    config = load_config("config.yaml")
    config.mode = "paper"

    db = Path(DB_PATH)
    if db.exists():
        db.unlink()
    storage = Storage(DB_PATH)

    exchange = Exchange(config)

    for symbol in SYMBOLS:
        try:
            candles = exchange.fetch_ohlcv_history(symbol, TIMEFRAME, total=LIMIT)
        except Exception as e:
            print(f"[SKIP] {symbol}: {e}")
            continue

        inst = Instrument(
            symbol=symbol,
            category="volumen_explosivo",
            strategy_name="volume_surge",
            strategy_params=STRATEGY_PARAMS,
            stop_loss_pct=RISK_OVERRIDES["stop_loss_pct"],
            take_profit_pct=RISK_OVERRIDES["take_profit_pct"],
            trailing_stop_pct=RISK_OVERRIDES["trailing_stop_pct"],
            partial_take_profit_pct=RISK_OVERRIDES["partial_take_profit_pct"],
            position_size_pct=0.15,
            use_atr_trailing=True,
            atr_trailing_mult=3.0,
            timeframe=TIMEFRAME,
        )

        strat = build_strategy("volume_surge", STRATEGY_PARAMS)
        execution = PaperExecutionEngine(config)
        risk = RiskManager(config.risk)
        # Override instruments so engine.config.instrument(symbol) works
        config.instruments = [inst]
        engine = Engine(
            config, strategies={symbol: strat}, risk=risk,
            execution=execution, storage=storage, enforce_daily_loss=False,
        )
        warmup = strat.min_candles
        for i in range(warmup, len(candles) + 1):
            engine.process(symbol, candles.iloc[:i])

        print(f"[OK] {symbol}: {len(candles)} velas procesadas")

    print()
    print(render_report(storage, quote="USDT", starting_balance=config.risk.starting_balance))
    storage.close()


if __name__ == "__main__":
    main()
