"""Motor de ejecución real contra KuCoin.

ATENCIÓN: envía órdenes con dinero real. Sólo se instancia con mode=live y
credenciales válidas. Úsalo únicamente tras validar la estrategia en paper.

Endurecido para dinero real:
  - Compras por importe en USDT (semántica de KuCoin), ventas por cantidad base.
  - Comprueba el tamaño mínimo de orden y la precisión; si no se cumple, lanza
    OrderRejected (el motor lo captura y no rompe el bucle).
"""

from __future__ import annotations

import logging

from ..config import Config
from ..exchange import Exchange
from ..models import Fill, Order, Side
from .base import OrderRejected

logger = logging.getLogger(__name__)


class LiveExecutionEngine:
    def __init__(self, config: Config, exchange: Exchange):
        self.config = config
        self.exchange = exchange
        self.quote_currency = config.risk.quote_currency

    def execute(self, order: Order) -> Fill:
        symbol = order.symbol
        if self.config.exchange == "kucoinfutures" and ":" not in symbol:
            symbol = f"{symbol}:USDT"

        if self.config.exchange == "kucoinfutures":
            notional = order.amount * order.price
            contracts = self.exchange.contracts_for_notional(symbol, notional, order.price)
            if contracts <= 0:
                raise OrderRejected(f"{symbol}: contratos calculados = 0 para notional {notional:.2f}")

            result = self.exchange.create_futures_order(symbol, order.side.value, contracts)
            return self._to_fill_futures(order, result, symbol)
        else:
            limits = self.exchange.market_limits(symbol)
            if order.side is Side.BUY:
                cost = order.amount * order.price
                min_cost = limits.get("min_cost")
                if min_cost and cost < min_cost:
                    raise OrderRejected(
                        f"{symbol}: coste {cost:.4f} {self.quote_currency} < mínimo {min_cost}"
                    )
                result = self.exchange.create_market_buy(symbol, cost)
            else:
                amount = self.exchange.amount_to_precision(symbol, order.amount)
                if amount <= 0:
                    raise OrderRejected(f"{symbol}: cantidad tras redondeo = 0")
                min_amount = limits.get("min_amount")
                if min_amount and amount < min_amount:
                    raise OrderRejected(
                        f"{symbol}: cantidad {amount} < mínimo {min_amount}"
                    )
                result = self.exchange.create_market_sell(symbol, amount)

            return self._to_fill(order, result)

    def _to_fill(self, order: Order, result: dict) -> Fill:
        filled_price = float(result.get("average") or result.get("price") or order.price)
        filled_amount = float(result.get("filled") or order.amount)
        fee_info = result.get("fee") or {}
        fee = float(fee_info.get("cost") or 0.0)
        logger.info(
            "[LIVE] %s %.8f %s @ %.6f (fee %.4f)",
            order.side.value.upper(), filled_amount, order.symbol, filled_price, fee,
        )
        return Fill(order=order, filled_price=filled_price,
                    filled_amount=filled_amount, fee=fee)

    def _to_fill_futures(self, order: Order, result: dict, symbol: str) -> Fill:
        filled_price = float(result.get("average") or result.get("price") or order.price)
        filled_contracts = float(result.get("filled") or (order.amount / self.exchange.contract_size(symbol)))
        filled_amount = filled_contracts * self.exchange.contract_size(symbol)
        fee_info = result.get("fee") or {}
        fee = float(fee_info.get("cost") or 0.0)
        logger.info(
            "[LIVE FUTURES] %s %.8f %s (%.1f contratos) @ %.6f (fee %.4f)",
            order.side.value.upper(), filled_amount, order.symbol, filled_contracts, filled_price, fee,
        )
        return Fill(order=order, filled_price=filled_price,
                    filled_amount=filled_amount, fee=fee)

    def get_balance(self) -> float:
        # Si es kucoinfutures, el balance devuelto es de la cuenta de futuros.
        currency = self.quote_currency
        return self.exchange.fetch_balance(currency)
