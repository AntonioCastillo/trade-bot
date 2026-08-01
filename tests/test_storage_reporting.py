from datetime import datetime, timedelta, timezone

from tradebot.models import ClosedTrade, Side
from tradebot.reporting import render_report
from tradebot.storage import Storage


def _trade(symbol, category, pnl, opened=None):
    opened = opened or datetime(2024, 1, 1, tzinfo=timezone.utc)
    return ClosedTrade(
        symbol=symbol, category=category, strategy_name="mean_reversion",
        side=Side.BUY, amount=1.0, entry_price=100.0, exit_price=100.0 + pnl,
        fee_total=0.2, pnl_abs=pnl, pnl_pct=pnl, exit_reason="take-profit",
        opened_at=opened, closed_at=opened + timedelta(hours=2),
    )


def test_summary_aggregates_pnl_and_winrate():
    st = Storage(":memory:")
    st.record_closed_trade(_trade("BTC/USDT", "majors", 10))
    st.record_closed_trade(_trade("BTC/USDT", "majors", -4))
    st.record_closed_trade(_trade("DOGE/USDT", "memecoins", 6))

    s = st.summary()
    assert s["trades"] == 3
    assert s["pnl_abs"] == 12
    assert s["wins"] == 2
    assert abs(s["win_rate"] - 2 / 3) < 1e-9


def test_summary_by_category():
    st = Storage(":memory:")
    st.record_closed_trade(_trade("BTC/USDT", "majors", 10))
    st.record_closed_trade(_trade("DOGE/USDT", "memecoins", -5))

    rows = {r["grp"]: r for r in st.summary_by("category")}
    assert rows["majors"]["pnl_abs"] == 10
    assert rows["memecoins"]["pnl_abs"] == -5


def test_render_report_contains_sections():
    st = Storage(":memory:")
    st.record_closed_trade(_trade("BTC/USDT", "majors", 10))
    text = render_report(st)
    assert "INFORME DE SIMULACIÓN" in text
    assert "POR CATEGORÍA" in text
    assert "BTC/USDT" in text


def test_render_report_empty():
    st = Storage(":memory:")
    assert "Todavía no hay operaciones" in render_report(st)
