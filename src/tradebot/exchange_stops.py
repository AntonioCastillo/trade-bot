"""Stops de emergencia en el exchange (solo modo live).

El bot decide sus salidas sondeando el precio y vendiendo a mercado. Si el
proceso o el servidor se caen, las posiciones abiertas quedarían sin stop. Este
módulo mantiene, por cada posición, una orden de stop a mercado EN KuCoin, un
poco por debajo del stop del bot (`exchange_stop_buffer_pct`), que actúa solo si
el bot no llega a vender antes: red de seguridad, no sustituto del stop normal.

Cómo se evita el mayor riesgo (una orden que sobreviva a su posición y venda una
posterior de la misma moneda, porque KuCoin no bloquea saldo para estas órdenes):
  - cada orden lleva un `clientOid` con el prefijo CLIENT_PREFIX;
  - antes de cualquier venta del bot se cancela la orden de la posición;
  - en cada ciclo y al arrancar se cancelan las órdenes con ese prefijo que no
    correspondan a una posición abierta (`cancel_orphans`).

Nada de esto llama al exchange si `engine.exchange_stops` es false.
"""

from __future__ import annotations

import logging
import time
import uuid

from .models import Position, Side

logger = logging.getLogger(__name__)

CLIENT_PREFIX = "tbstop-"
GONE_RATIO = 0.05          # saldo real < 5% del registrado -> la posición ya no existe
AMOUNT_TOLERANCE = 0.01    # reponer la orden si la cantidad cambió más de un 1%
RETRY_SECONDS = 300.0      # tras un fallo al crear la orden, no reintentar antes de esto


class StopGuard:
    def __init__(self, exchange, buffer_pct: float = 0.02, min_move_pct: float = 0.005, enabled: bool = True):
        self.exchange = exchange
        self.buffer_pct = buffer_pct
        self.min_move_pct = min_move_pct
        self.enabled = bool(enabled and exchange is not None)
        self._created: dict[str, float] = {}       # id -> instante de creación (el listado puede ir con retraso)
        self._retry_after: dict[str, float] = {}   # símbolo -> no reintentar la creación antes de este instante

    # --- nivel deseado -------------------------------------------------------------

    def target_price(self, pos: Position) -> float:
        """Disparo de la orden: el stop del bot menos el margen."""
        return pos.stop_loss * (1 - self.buffer_pct)

    def _needs_update(self, pos: Position) -> bool:
        if not pos.stop_order_id:
            return True
        if pos.stop_order_amount <= 0 or abs(pos.amount / pos.stop_order_amount - 1) > AMOUNT_TOLERANCE:
            return True
        # Solo se sube: el stop del bot nunca baja, y reponer por cada décima satura al exchange.
        return self.target_price(pos) >= pos.stop_order_price * (1 + self.min_move_pct)

    # --- operaciones ---------------------------------------------------------------

    def sync(self, pos: Position) -> bool:
        """Deja en el exchange la orden que corresponde a la posición (la crea o la
        repone si el stop subió lo bastante o cambió la cantidad). Devuelve True si
        cambió algo. Un fallo no interrumpe nada: la posición sigue con el stop del bot."""
        if not self.enabled or pos.side is not Side.BUY or pos.amount <= 0 or not self._needs_update(pos):
            return False
        if time.monotonic() < self._retry_after.get(pos.symbol, 0.0):
            return False                              # falló hace poco: no se insiste en cada sondeo
        price = self.target_price(pos)
        amount = self._sellable_amount(pos)
        try:
            order = self.exchange.create_stop_sell(pos.symbol, amount, price, CLIENT_PREFIX + uuid.uuid4().hex[:24])
        except Exception as exc:
            self._retry_after[pos.symbol] = time.monotonic() + RETRY_SECONDS
            logger.warning("[%s] No pude poner el stop de emergencia en el exchange (%s); sigue el stop del bot "
                           "y lo reintento en %d min", pos.symbol, exc, RETRY_SECONDS // 60)
            return False
        self._retry_after.pop(pos.symbol, None)
        old = pos.stop_order_id
        pos.stop_order_id = str(order["id"])
        pos.stop_order_price = float(order.get("trigger_price") or price)
        pos.stop_order_amount = float(order.get("amount") or pos.amount)
        self._created[pos.stop_order_id] = time.monotonic()
        logger.info("[%s] Stop de emergencia en el exchange: %.8f a %.6f (orden %s)",
                    pos.symbol, pos.stop_order_amount, pos.stop_order_price, pos.stop_order_id)
        if old:                                   # la nueva ya protege: ahora se retira la anterior
            self._cancel(old, pos.symbol)
        return True

    def _sellable_amount(self, pos: Position) -> float:
        """Cantidad de la orden: nunca más de lo que hay de verdad en la cuenta. Si la
        comisión de compra se cobró en la propia moneda hay algo menos de lo registrado,
        y una orden por más saldo del disponible NO se ejecutaría al dispararse."""
        try:
            real = float(self.exchange.fetch_balance(pos.symbol.split("/")[0]))
        except Exception:
            return pos.amount * 0.998                 # sin dato: un pequeño margen de seguridad
        return real if 0 < real < pos.amount else pos.amount

    def release(self, pos: Position) -> str:
        """Retira la orden antes de que el bot venda. Devuelve:
        'none' (no había), 'cancelled' (retirada), 'missing' (ya no estaba viva: puede
        haberse ejecutado) o 'error' (no se pudo hablar con el exchange)."""
        if not self.enabled or not pos.stop_order_id:
            return "none"
        try:
            cancelled = bool(self.exchange.cancel_stop_order(pos.stop_order_id, pos.symbol))
        except Exception as exc:
            logger.warning("[%s] No pude cancelar la orden de stop %s (%s)", pos.symbol, pos.stop_order_id, exc)
            return "error"
        if cancelled:
            pos.stop_order_id, pos.stop_order_price, pos.stop_order_amount = "", 0.0, 0.0
            return "cancelled"
        return "missing"

    def _cancel(self, order_id: str, symbol: str) -> bool:
        try:
            return bool(self.exchange.cancel_stop_order(order_id, symbol))
        except Exception as exc:
            logger.warning("[%s] No pude cancelar la orden de stop %s (%s)", symbol, order_id, exc)
            return False

    def is_recent(self, order_id: str, seconds: float = 120.0) -> bool:
        """Orden creada hace poco: puede no salir todavía en el listado del exchange."""
        created = self._created.get(order_id)
        return created is not None and time.monotonic() - created < seconds

    def cancel_all(self, positions: list[Position]) -> int:
        """Retira todas las órdenes del bot (al desactivar la opción). Ignora `enabled`."""
        if self.exchange is None:
            return 0
        n = 0
        try:
            orders = self.exchange.fetch_open_stop_orders()
        except Exception as exc:
            logger.warning("No pude listar las órdenes de stop del exchange (%s)", exc)
            orders = []
        ids = {str(o["id"]): o.get("symbol") or "" for o in orders if str(o.get("client_id") or "").startswith(CLIENT_PREFIX)}
        for pos in positions:
            if pos.stop_order_id:
                ids.setdefault(pos.stop_order_id, pos.symbol)
        for order_id, symbol in ids.items():
            n += bool(self._cancel(order_id, symbol))
        return n

    def position_gone(self, pos: Position) -> bool | None:
        """¿Ya no está el activo en la cuenta? None si no se pudo consultar."""
        try:
            real = float(self.exchange.fetch_balance(pos.symbol.split("/")[0]))
        except Exception as exc:
            logger.warning("[%s] No pude leer el saldo para comprobar el stop del exchange (%s)", pos.symbol, exc)
            return None
        return pos.amount > 0 and real / pos.amount < GONE_RATIO

    def open_orders(self) -> dict[str, dict] | None:
        """Órdenes de stop vivas creadas por el bot: {id: orden}. None si falla la consulta."""
        if not self.enabled:
            return {}
        try:
            orders = self.exchange.fetch_open_stop_orders()
        except Exception as exc:
            logger.warning("No pude listar las órdenes de stop del exchange (%s)", exc)
            return None
        return {str(o["id"]): o for o in orders if str(o.get("client_id") or "").startswith(CLIENT_PREFIX)}

    def cancel_orphans(self, positions: list[Position], open_orders: dict[str, dict]) -> tuple[int, list[str]]:
        """Cancela las órdenes del bot que no pertenecen a ninguna posición abierta.
        Devuelve (canceladas, [las que NO se pudieron cancelar])."""
        wanted = {p.stop_order_id for p in positions if p.stop_order_id}
        n, failed = 0, []
        for order_id, order in open_orders.items():
            if order_id in wanted:
                continue
            if self._cancel(order_id, order.get("symbol") or ""):
                n += 1
                logger.warning("Orden de stop huérfana cancelada: %s (%s)", order_id, order.get("symbol"))
            else:
                failed.append(f"{order.get('symbol')} {order_id}")
        return n, failed
