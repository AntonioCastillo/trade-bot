"""Radar de Tasas de Financiación Extremas (Funding Rate Radar).

Escanea periódicamente el mercado de derivados en busca de oportunidades de
financiación anormalmente elevadas (>25% anual por defecto).

NO ejecuta operaciones ni inmoviliza capital: es 100% informativo y emite
alertas directas a Telegram con cooldown inteligente para no spamear.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .carry import annualized_pct
from .config import Config
from .exchange import Exchange
from .notifier import Notifier, NullNotifier

logger = logging.getLogger(__name__)

DEFAULT_RADAR_POOL = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
    "ADA/USDT", "NEAR/USDT", "LINK/USDT", "AVAX/USDT", "SUI/USDT",
    "TRX/USDT", "DOT/USDT", "LTC/USDT", "ATOM/USDT", "INJ/USDT",
]


def evaluate_funding_radar(
    config: Config,
    exchange: Exchange,
    notifier: Notifier | None = None,
    cooldowns: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Escanea los contratos perpetuos y alerta si alguno supera el umbral de funding anualizado."""
    cfg = config.carry
    if not getattr(cfg, "funding_radar_enabled", True):
        return []

    notifier = notifier or NullNotifier()
    if cooldowns is None:
        cooldowns = {}

    threshold_pct = getattr(cfg, "radar_min_annualized_pct", 25.0)
    symbols = cfg.radar_symbols or DEFAULT_RADAR_POOL
    now = time.time()
    alerts: list[dict[str, Any]] = []

    for spot_sym in symbols:
        perp_sym = spot_sym if ":" in spot_sym else f"{spot_sym}:USDT"
        try:
            fh = exchange.fetch_funding_history(perp_sym, 1)
            if not fh:
                continue
            rate = float(fh[-1]["fundingRate"])
            ann = annualized_pct(rate)

            if ann >= threshold_pct:
                # Comprobar cooldown de 8 horas (28800s) por símbolo
                last_alert_time = cooldowns.get(spot_sym, 0.0)
                if (now - last_alert_time) >= 28800:
                    cooldowns[spot_sym] = now
                    alerts.append({
                        "symbol": spot_sym,
                        "perp_symbol": perp_sym,
                        "rate": rate,
                        "rate_pct_8h": rate * 100,
                        "annualized_pct": ann,
                    })
        except Exception:
            logger.debug("[RADAR-FUNDING] No pude leer funding rate de %s", spot_sym)
            continue

    if alerts:
        if len(alerts) == 1:
            a = alerts[0]
            msg = (
                f"📡 <b>RADAR DE FUNDING: Oportunidad Detectada</b>\n\n"
                f"• <b>Símbolo:</b> <code>{a['symbol']}</code>\n"
                f"• <b>Tasa 8h:</b> <b>{a['rate_pct_8h']:+.4f}%</b>\n"
                f"• <b>Tasa Anualizada:</b> <b>{a['annualized_pct']:+.1f}% anual</b>\n"
                f"• <i>Alta demanda compradora de apalancamiento en derivados.</i>"
            )
        else:
            lines = [
                "📡 <b>RADAR DE FUNDING: Múltiples Oportunidades</b>\n",
                f"<i>Tasas de financiación anualizadas > {threshold_pct:.0f}%:</i>\n",
            ]
            for a in alerts:
                lines.append(
                    f"• <b>{a['symbol']}:</b> <b>{a['annualized_pct']:+.1f}% anual</b> "
                    f"({a['rate_pct_8h']:+.4f}% 8h)"
                )
            msg = "\n".join(lines)

        notifier.notify(msg)
        logger.info("[RADAR-FUNDING] Alerta enviada para %d símbolos", len(alerts))

    return alerts
