from datetime import datetime, timedelta, timezone

from tradebot.daemon import write_report_snapshot
from tradebot.models import ClosedTrade, Side
from tradebot.storage import Storage


def _trade(symbol, pnl):
    opened = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return ClosedTrade(
        symbol=symbol, category="majors", strategy_name="mean_reversion",
        side=Side.BUY, amount=1.0, entry_price=100.0, exit_price=100.0 + pnl,
        fee_total=0.2, pnl_abs=pnl, pnl_pct=pnl, exit_reason="take-profit",
        opened_at=opened, closed_at=opened + timedelta(hours=1),
    )


def test_write_report_snapshot_creates_file(tmp_path):
    st = Storage(":memory:")
    st.record_closed_trade(_trade("BTC/USDT", 10))
    path = tmp_path / "sub" / "report.txt"

    text = write_report_snapshot(st, "USDT", str(path))

    assert path.exists()
    saved = path.read_text(encoding="utf-8")
    assert saved == text
    assert "BTC/USDT" in saved
    assert "P&L total" in saved
