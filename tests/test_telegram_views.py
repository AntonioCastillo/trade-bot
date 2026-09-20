from unittest.mock import MagicMock

from tradebot.config import Config, Instrument
from tradebot.models import Position, Side
from tradebot.telegram_views import (
    render_daily_report_telegram,
    render_heads_summary,
    render_rs_rotations,
    render_welcome_message,
)


def test_render_heads_summary():
    cfg = Config()
    cfg.instruments = [
        Instrument("BTC/USDT", "majors", "trend", {}, 0.03, 0.06, 0.2),
        Instrument("ETH/USDT", "majors", "trend", {}, 0.03, 0.06, 0.2),
        Instrument("SOL/USDT", "altcoins", "trend", {}, 0.03, 0.06, 0.2),
    ]
    summary = render_heads_summary(cfg)
    assert "majors" in summary
    assert "BTC, ETH" in summary
    assert "altcoins" in summary
    assert "SOL" in summary


def test_render_welcome_message():
    cfg = Config()
    cfg.instruments = [
        Instrument("BTC/USDT", "majors", "trend", {}, 0.03, 0.06, 0.2),
    ]
    msg = render_welcome_message(cfg, equity=1500.0)
    assert "1,500.00 USDT" in msg
    assert "Cabezas Activas" in msg
    assert "Stop Loss base" in msg


def test_render_rs_rotations():
    rotations = [
        {
            "category": "momentum_rotativo",
            "new_syms": ["SOL/USDT", "AVAX/USDT"],
            "old_syms": ["DOT/USDT", "ADA/USDT"],
        }
    ]
    msg = render_rs_rotations(rotations)
    assert "ROTACIÓN RS EN VIVO" in msg
    assert "SOL/USDT, AVAX/USDT" in msg
    assert "DOT/USDT, ADA/USDT" in msg


def test_render_daily_report_telegram():
    engine = MagicMock()
    engine.equity.return_value = 1750.50
    engine.risk.halted = False
    engine.storage.summary.return_value = {
        "pnl_abs": 45.2,
        "trades": 12,
        "win_rate": 0.75,
    }
    engine.storage.total_funding_collected.return_value = 2.35
    engine.positions = [
        Position(
            symbol="BTC/USDT",
            side=Side.BUY,
            amount=0.01,
            entry_price=60000.0,
            stop_loss=58000.0,
            take_profit=65000.0,
        )
    ]
    engine.last_prices = {"BTC/USDT": 61000.0}
    engine.carry_runner = None

    cfg = Config()
    cfg.instruments = [
        Instrument("BTC/USDT", "majors", "trend", {}, 0.03, 0.06, 0.2),
    ]

    report = render_daily_report_telegram(engine, cfg)
    assert "ESTADO GLOBAL DE LA CARTERA" in report
    assert "1,750.50 USDT" in report
    assert "+47.55 USDT" in report  # 45.2 + 2.35
    assert "BTC/USDT" in report
    assert "POSICIONES ABIERTAS SPOT" in report
