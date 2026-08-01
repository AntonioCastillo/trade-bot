"""Genera informes legibles a partir de las operaciones cerradas persistidas."""

from __future__ import annotations

import math

from .metrics import metrics_from_pnls
from .storage import Storage


def _fmt_row(cells: list[str], widths: list[int]) -> str:
    return "  ".join(c.ljust(w) for c, w in zip(cells, widths))


def render_report(
    storage: Storage,
    quote: str = "USDT",
    starting_balance: float = 10_000.0,
    limit: int = 20,
) -> str:
    lines: list[str] = []
    s = storage.summary()

    lines.append("=" * 64)
    lines.append("INFORME DE SIMULACIÓN")
    lines.append("=" * 64)
    if s["trades"] == 0:
        lines.append("Todavía no hay operaciones cerradas registradas.")
        return "\n".join(lines)

    lines.append(f"Operaciones cerradas: {s['trades']}")
    lines.append(f"Aciertos:             {s['wins']} ({s['win_rate'] * 100:.1f}% win rate)")
    lines.append(f"P&L total:            {s['pnl_abs']:+.2f} {quote}")
    lines.append(f"P&L medio/operación:  {s['avg_pnl_pct']:+.2f}%")

    # --- Métricas de robustez -----------------------------------------------------
    rows = storage.all_trades()
    m = metrics_from_pnls(
        [r["pnl_abs"] for r in rows], [r["pnl_pct"] for r in rows], starting_balance
    )
    pf = "inf" if math.isinf(m.profit_factor) else f"{m.profit_factor:.2f}"
    lines.append("")
    lines.append("ROBUSTEZ")
    lines.append(f"Rentabilidad total:   {m.return_pct:+.2f}% (sobre {starting_balance:.0f} {quote})")
    lines.append(f"Profit factor:        {pf}   (>1 = rentable)")
    lines.append(f"Max drawdown:         {m.max_drawdown_pct:.2f}%")
    lines.append(f"Sharpe (por op.):     {m.sharpe:.2f}")

    # --- Desglose por categoría y por símbolo -------------------------------------
    for dim, title in (("category", "POR CATEGORÍA"), ("symbol", "POR SÍMBOLO")):
        lines.append("")
        lines.append(title)
        widths = [14, 7, 6, 14, 10]
        lines.append(_fmt_row(["grupo", "ops", "win%", f"P&L {quote}", "P&L% medio"], widths))
        lines.append("-" * 60)
        for r in storage.summary_by(dim):
            wr = (r["wins"] / r["trades"] * 100) if r["trades"] else 0
            lines.append(_fmt_row([
                str(r["grp"]), str(r["trades"]), f"{wr:.0f}",
                f"{r['pnl_abs']:+.2f}", f"{r['avg_pnl_pct']:+.2f}",
            ], widths))

    # --- Últimas operaciones -------------------------------------------------------
    lines.append("")
    lines.append(f"ÚLTIMAS {limit} OPERACIONES")
    widths = [12, 6, 12, 12, 12, 12]
    lines.append(_fmt_row(["símbolo", "lado", "entrada", "salida", f"P&L {quote}", "salida por"], widths))
    lines.append("-" * 72)
    for r in storage.all_trades()[-limit:]:
        lines.append(_fmt_row([
            r["symbol"], r["side"], f"{r['entry_price']:.6f}",
            f"{r['exit_price']:.6f}", f"{r['pnl_abs']:+.2f}", r["exit_reason"],
        ], widths))

    lines.append("")
    lines.append("Nota: rendimiento pasado NO garantiza resultados futuros.")
    return "\n".join(lines)
