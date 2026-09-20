"""Vistas y formateadores de mensajes HTML para Telegram.

Desacopla la capa de presentación/notificaciones del orquestador del daemon.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import Config
    from .engine import Engine


def render_heads_summary(config: Config) -> str:
    """Resumen compacto de las cabezas activas agrupadas por estrategia y subsistemas."""
    from collections import OrderedDict
    groups: "OrderedDict[str, list[str]]" = OrderedDict()
    for ins in config.instruments:
        groups.setdefault(ins.category, []).append(ins.symbol.split("/")[0])
    lines = [f"• {cat}: {', '.join(syms)}" for cat, syms in groups.items()]
    if getattr(config.xsmom, "enabled", False):
        lines.append(f"• xsmom (momentum transversal, top-{config.xsmom.top_k})")
    if getattr(config.sniper, "enabled", False):
        lines.append("• sniper (recién listadas)")
    if getattr(config.carry, "enabled", False):
        lines.append("• carry (funding)")
    return "\n".join(lines) if lines else "(ninguna)"


def render_daily_report_telegram(engine: Engine, config: Config) -> str:
    """Informe consolidado y completo de la cartera para Telegram."""
    s = engine.storage.summary()
    quote = config.risk.quote_currency
    try:
        equity = engine.equity()
        eq_str = f"{equity:,.2f} {quote}"
    except Exception:
        eq_str = "n/d"

    # Extraer métricas de Carry Trade si está activo o persistido
    funding_total = 0.0
    if engine.storage is not None:
        try:
            funding_total = engine.storage.total_funding_collected()
        except Exception:
            funding_total = 0.0

    carry_lines = []
    carry_runner = getattr(engine, "carry_runner", None)
    if carry_runner is not None and getattr(carry_runner, "mgr", None) is not None:
        active_funding_sum = 0.0
        for cp in carry_runner.mgr.positions.values():
            f_col = getattr(cp, "funding_collected", 0.0)
            active_funding_sum += f_col
            carry_lines.append(
                f"• <b>{cp.symbol}</b> (${getattr(cp, 'notional', 0.0):.2f})\n"
                f"  Funding cobrado activo: <b>{f_col:+.4f} {quote}</b> (Delta-Neutral)"
            )
        if funding_total == 0.0 and active_funding_sum > 0.0:
            funding_total = active_funding_sum

    net_realized = s["pnl_abs"] + funding_total

    lines = [
        f"📊 <b>ESTADO GLOBAL DE LA CARTERA</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 <b>Patrimonio Total:</b> {eq_str}",
        f"💵 <b>Beneficio Neto Realizado:</b> <b>{net_realized:+.2f} {quote}</b>",
        f"   • Spot Realizado: {s['pnl_abs']:+.2f} {quote} ({s['trades']} ops, {s['win_rate']*100:.1f}% WR)",
        f"   • Funding Carry Histórico: {funding_total:+.4f} {quote}",
        f"🛡️ <b>Estado:</b> {'🟢 OPERANDO' if not engine.risk.halted else '🔴 DETENIDO (' + engine.risk.halted_reason + ')'}",
        "",
    ]

    # Posiciones abiertas desglosadas
    if engine.positions:
        lines.append("🔓 <b>POSICIONES ABIERTAS SPOT:</b>")
        for p in engine.positions:
            curr_p = engine.last_prices.get(p.symbol, p.entry_price)
            direction = 1 if p.side.value == "buy" else -1
            pnl_abs = (curr_p - p.entry_price) * p.amount * direction
            pnl_pct = (pnl_abs / (p.entry_price * p.amount) * 100) if (p.entry_price * p.amount) else 0.0
            tp_info = f"SL: {p.stop_loss:.4f} | TP: {p.take_profit:.4f}"
            if p.partial_tp_done:
                tp_info += " [TP1 COBRADO 50%]"
            lines.append(
                f"• <b>{p.symbol}</b> ({p.side.value.upper()})\n"
                f"  Entrada: {p.entry_price:.4f} → Actual: {curr_p:.4f}\n"
                f"  P&L: <b>{pnl_abs:+.2f} {quote} ({pnl_pct:+.2f}%)</b>\n"
                f"  <i>{tp_info}</i>"
            )
        lines.append("")
    else:
        lines.append("💤 <b>Posiciones Spot:</b> 0 (100% USDT Líquido)\n")

    # Sección Carry Trade (si hay posiciones)
    if carry_lines:
        lines.append("⚖️ <b>CARRY TRADE (Delta-Neutral):</b>")
        lines.extend(carry_lines)
        lines.append("")

    lines.append("🐲 <b>Cabezas Activas:</b>")
    lines.append(render_heads_summary(config))

    return "\n".join(lines)


def render_welcome_message(config: Config, equity: float | None = None) -> str:
    """Mensaje inicial de bienvenida al arrancar el daemon."""
    quote = config.risk.quote_currency
    eq_str = f"{equity:,.2f} {quote}" if equity is not None else "Consultando balance..."
    mode_emoji = "🔴 REAL" if config.mode == "live" else "🧪 PAPER"

    lines = [
        f"🤖 <b>Bot iniciado [{mode_emoji}]</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 <b>Balance Inicial:</b> {eq_str}",
        f"🛡️ <b>Gestión de Riesgo:</b>",
        f"   • Stop Loss base: {config.risk.stop_loss_pct*100:.1f}%",
        f"   • Cortafuegos diario: máx {config.risk.max_daily_loss_pct*100:.0f}% pérdida",
        f"   • Drawdown máx cuenta: {config.risk.max_account_drawdown_pct*100:.0f}%",
        "",
        "🐲 <b>Cabezas Activas:</b>",
        render_heads_summary(config),
    ]

    subs = []
    if getattr(config.carry, "funding_radar_enabled", False):
        subs.append(f"• Radar de Funding (> {config.carry.radar_min_annualized_pct:.0f}% anual)")
    if getattr(config.carry, "enabled", False):
        subs.append("• Carry Trade delta-neutral")
    if getattr(config.sniper, "enabled", False):
        subs.append("• Sniper de lanzamientos")
    if getattr(config.xsmom, "enabled", False):
        subs.append("• Momentum transversal")

    if subs:
        lines.append("\n⚙️ <b>Subsistemas:</b>")
        lines.extend(subs)

    return "\n".join(lines)


def render_rs_rotations(rotations: list[dict[str, Any]]) -> str:
    """Mensaje formateado para rotaciones de Fuerza Relativa (RS vs BTC)."""
    if len(rotations) == 1:
        rot = rotations[0]
        return (
            f"🔄 <b>ROTACIÓN RS EN VIVO</b> ({rot['category']})\n"
            f"Nuevos símbolos activos: {', '.join(rot['new_syms'])}\n"
            f"Símbolos anteriores: {', '.join(rot['old_syms'])}"
        )
    lines = ["🔄 <b>ROTACIÓN DE FUERZA RELATIVA (RS vs BTC)</b>"]
    for rot in rotations:
        lines.append(
            f"\n• <b>{rot['category']}</b>\n"
            f"  Nuevos: {', '.join(rot['new_syms'])}\n"
            f"  Anteriores: {', '.join(rot['old_syms'])}"
        )
    return "\n".join(lines)
