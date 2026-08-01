"""Verificación de la API real: una compra y venta pequeñas de ida y vuelta
para comprobar que las órdenes reales funcionan de punta a punta.

La pérdida esperada es solo comisiones + slippage (unos céntimos con 1 USD): el
objetivo es validar la integración con KuCoin, no ganar dinero.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .exchange import Exchange
from .notifier import Notifier, NullNotifier

logger = logging.getLogger(__name__)


@dataclass
class ApiCheckResult:
    symbol: str
    amount: float
    buy_price: float
    sell_price: float
    cost: float          # USDT gastados en la compra
    proceeds: float      # USDT recuperados en la venta
    net: float           # proceeds - cost (negativo = coste de la validación)


def run_api_check(
    exchange: Exchange,
    symbol: str,
    usd: float,
    quote: str = "USDT",
    notifier: Notifier | None = None,
) -> ApiCheckResult:
    """Compra `usd` de `symbol` a mercado y lo vende inmediatamente. REAL."""
    n = notifier or NullNotifier()
    n.notify(f"🔎 <b>Verificación API</b>: comprando ~{usd} {quote} de {symbol}…")

    buy = exchange.create_market_buy(symbol, usd)
    amount = float(buy.get("filled") or buy.get("amount") or 0.0)
    if amount <= 0:
        raise RuntimeError(f"La compra no devolvió cantidad ejecutada: {buy}")
    cost = float(buy.get("cost") or usd)
    buy_price = float(buy.get("average") or buy.get("price") or (cost / amount))

    # Vender el saldo LIBRE real de la moneda base (la compra pudo cobrar la
    # comisión en esa misma moneda, dejando un poco menos de lo comprado).
    base = symbol.split("/")[0]
    try:
        free_base = exchange.fetch_balance(base)
    except Exception:
        free_base = 0.0
    # min(): vende como mucho lo comprado, sin tocar saldo previo de esa moneda,
    # pero acotado al saldo libre real (por la comisión cobrada en base).
    sell_amount = min(amount, free_base) if free_base > 0 else amount

    try:
        sell = exchange.create_market_sell(symbol, sell_amount)
    except Exception as e:
        n.notify(
            f"⚠️ <b>Compra OK, VENTA falló</b> {symbol}\n"
            f"Tienes ~{sell_amount} {base} sin vender en la cuenta. Véndelo a mano.\n{e}"
        )
        raise RuntimeError(
            f"Compra ejecutada ({sell_amount} {base}) pero la venta falló: {e}"
        ) from e

    proceeds = float(sell.get("cost") or 0.0)
    sell_price = float(sell.get("average") or sell.get("price") or (proceeds / sell_amount if sell_amount else 0.0))

    net = proceeds - cost
    result = ApiCheckResult(symbol, sell_amount, buy_price, sell_price, cost, proceeds, net)
    logger.info(
        "Verificación API OK | %s compra %.8f @ %.6f, venta @ %.6f | neto %.4f %s",
        symbol, amount, buy_price, sell_price, net, quote,
    )
    emoji = "✅" if net >= 0 else "☑️"
    n.notify(
        f"{emoji} <b>API verificada</b> {symbol}\n"
        f"Compra: {buy_price:.6f}  →  Venta: {sell_price:.6f}\n"
        f"Coste de la validación: {net:+.4f} {quote}"
    )
    return result
