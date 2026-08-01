"""Utilidades compartidas por los tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradebot.config import Config, Instrument, RiskConfig


@pytest.fixture
def price_series():
    """Genera una serie de precios sintética y reproducible."""

    def _make(prices: list[float]) -> pd.DataFrame:
        idx = pd.date_range("2024-01-01", periods=len(prices), freq="1h", tz="UTC")
        close = pd.Series(prices, index=idx)
        return pd.DataFrame(
            {
                "open": close.shift(1).fillna(close),
                "high": close * 1.001,
                "low": close * 0.999,
                "close": close,
                "volume": np.full(len(prices), 100.0),
            },
            index=idx,
        )

    return _make


def make_instrument(
    symbol: str = "BTC/USDT",
    category: str = "majors",
    strategy_name: str = "mean_reversion",
    params: dict | None = None,
    stop_loss_pct: float = 0.03,
    take_profit_pct: float = 0.06,
    position_size_pct: float = 0.10,
    trailing_stop_pct: float = 0.0,
) -> Instrument:
    return Instrument(
        symbol=symbol, category=category, strategy_name=strategy_name,
        strategy_params=params or {}, stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct, position_size_pct=position_size_pct,
        trailing_stop_pct=trailing_stop_pct,
    )


def make_config(instrument: Instrument, slippage: float = 0.0, **risk) -> Config:
    cfg = Config(instruments=[instrument], risk=RiskConfig(**risk))
    cfg.engine.slippage_pct = slippage
    cfg.engine.fee_pct = 0.001
    return cfg
