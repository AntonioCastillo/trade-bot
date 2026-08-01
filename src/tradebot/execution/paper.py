"""Motor de ejecución simulado. Ejecuta órdenes contra un balance virtual,
aplicando comisiones y slippage. Sin red ni riesgo de dinero real.

El slippage modela que en el mercado real no compras/vendes exactamente al
precio de referencia: las compras se llenan algo por encima y las ventas algo
por debajo. Es clave para que las estrategias de entrada/salida rápida no den
resultados irrealmente buenos en simulación.
"""

from __future__ import annotations

import logging

from ..config import Config
from ..models import Fill, Order, Side

logger = logging.getLogger(__name__)


class PaperExecutionEngine:
    def __init__(self, config: Config):
        self.config = config
        self.fee_pct = config.engine.fee_pct
        self.slippage_pct = config.engine.slippage_pct
        self._balance = config.risk.starting_balance  # en moneda de cotización

    def execute(self, order: Order) -> Fill:
        # Aplica slippage según la dirección de la orden.
        if order.side is Side.BUY:
            filled_price = order.price * (1 + self.slippage_pct)
        else:
            filled_price = order.price * (1 - self.slippage_pct)

        notional = filled_price * order.amount
        fee = notional * self.fee_pct

        if order.side is Side.BUY:
            self._balance -= notional + fee
        else:  # SELL
            self._balance += notional - fee

        logger.info(
            "[PAPER] %s %.8f %s @ %.6f (fee %.4f) | balance=%.2f",
            order.side.value.upper(), order.amount, order.symbol,
            filled_price, fee, self._balance,
        )
        return Fill(order=order, filled_price=filled_price,
                    filled_amount=order.amount, fee=fee)

    def get_balance(self) -> float:
        return self._balance
