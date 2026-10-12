"""Comprueba contra KuCoin REAL las llamadas que usan los stops de emergencia.

Pone UNA orden de stop de venta por la cantidad mínima, con el disparo un 50% por
debajo del precio actual (no se va a ejecutar), la busca en el listado, la cancela
y verifica que una segunda cancelación se detecta como "ya no existe". No compra
ni vende nada. Ejecútalo antes de activar `engine.exchange_stops`.

Uso (en el VPS, con las claves del bot):
    python scripts/verify_stops.py                  # usa ETH/USDT
    python scripts/verify_stops.py --symbol DOGE/USDT
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.config import load_config  # noqa: E402
from tradebot.exchange import Exchange  # noqa: E402
from tradebot.exchange_stops import CLIENT_PREFIX  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Verifica las órdenes de stop contra KuCoin real")
    parser.add_argument("--symbol", default="ETH/USDT", help="Par a usar (def: ETH/USDT)")
    args = parser.parse_args()

    config = load_config()
    if not config.credentials.is_complete:
        print("Faltan las claves de KuCoin en .env")
        sys.exit(1)
    exchange = Exchange(config)
    symbol = args.symbol
    ok = True

    def step(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and passed
        print(f"  [{'OK' if passed else 'FALLO'}] {name}{' — ' + detail if detail else ''}")

    price = exchange.fetch_last_price(symbol)
    limits = exchange.market_limits(symbol)
    amount = float(limits.get("min_amount") or 0) * 2
    trigger = price * 0.5
    print(f"{symbol}: precio {price}, orden de prueba de {amount} con disparo en {trigger:.6f} (-50%: no se ejecutará)")
    if amount <= 0:
        print("No conozco la cantidad mínima de este par; prueba con otro --symbol")
        sys.exit(1)

    client_id = CLIENT_PREFIX + "verify" + uuid.uuid4().hex[:16]
    order_id = None
    try:
        order = exchange.create_stop_sell(symbol, amount, trigger, client_id)
        order_id = str(order["id"]) if order.get("id") else None
        step("crear la orden de stop", bool(order_id), f"id {order_id}, disparo {order['trigger_price']}, cantidad {order['amount']}")
        if not order_id:
            return

        found = None
        for _ in range(5):                       # el listado puede tardar un instante
            found = next((o for o in exchange.fetch_open_stop_orders() if str(o["id"]) == order_id), None)
            if found:
                break
            time.sleep(1.0)
        step("verla en el listado de órdenes de stop", found is not None)
        if found:
            step("el listado devuelve nuestro identificador", str(found.get("client_id") or "") == client_id, str(found.get("client_id")))
            step("el listado devuelve el par", bool(found.get("symbol")), str(found.get("symbol")))

        step("cancelarla", exchange.cancel_stop_order(order_id, symbol) is True)
        time.sleep(1.0)
        gone = all(str(o["id"]) != order_id for o in exchange.fetch_open_stop_orders())
        step("ya no aparece en el listado", gone)
        order_id = None if gone else order_id
        try:
            again = exchange.cancel_stop_order(order["id"], symbol)
            step("cancelar otra vez se detecta como 'ya no existe'", again is False, f"devolvió {again}")
        except Exception as exc:
            step("cancelar otra vez se detecta como 'ya no existe'", False, f"lanzó {type(exc).__name__}: {exc}")
    except Exception as exc:
        step("llamada al exchange", False, f"{type(exc).__name__}: {exc}")
    finally:
        if order_id:
            try:
                exchange.cancel_stop_order(order_id, symbol)
                print("  (orden de prueba retirada)")
            except Exception as exc:
                print(f"  ATENCIÓN: no pude retirar la orden de prueba {order_id}: {exc}. Cancélala a mano en KuCoin.")

    print("\nRESULTADO: " + ("todo correcto; se puede activar engine.exchange_stops" if ok else "hay fallos; NO actives engine.exchange_stops y pásame esta salida"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
