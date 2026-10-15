"""Comprueba contra el exchange REAL las llamadas que usan los stops de emergencia.

Pone UNA orden de stop de venta por la cantidad mínima, con el disparo un 50% por
debajo del precio actual (no se va a ejecutar), la busca en el listado, la cancela
y verifica que una segunda cancelación se detecta como "ya no existe". No compra
ni vende nada. Ejecútalo antes de activar `engine.exchange_stops`, y otra vez al
cambiar de exchange: cada uno tiene sus propias llamadas.

Uso (en el VPS, con las claves del bot):
    python scripts/verify_stops.py                  # usa ETH contra la moneda de cotización
    python scripts/verify_stops.py --symbol DOGE/USDT
    python scripts/verify_stops.py --config otra_config.yaml
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

from tradebot.config import credential_env_names, load_config  # noqa: E402
from tradebot.exchange import Exchange  # noqa: E402
from tradebot.exchange_stops import CLIENT_PREFIX  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Verifica las órdenes de stop contra el exchange real")
    parser.add_argument("--symbol", default=None, help="Par a usar (def: ETH contra la moneda de cotización)")
    parser.add_argument("--config", default="config.yaml", help="Fichero de configuración (def: config.yaml)")
    parser.add_argument("--exchange", default=None, help="Otro exchange con la misma configuración (p. ej. myokx)")
    args = parser.parse_args()

    config = load_config(args.config, require_credentials=False, exchange=args.exchange)
    if not config.credentials.is_complete:
        print(f"Faltan las claves de {config.exchange_name} en .env ({', '.join(credential_env_names(config.exchange))})")
        sys.exit(1)
    exchange = Exchange(config)
    symbol = args.symbol or f"ETH/{config.risk.quote_currency}"
    print(f"Exchange: {config.exchange_name}")
    ok = True

    def step(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and passed
        print(f"  [{'OK' if passed else 'FALLO'}] {name}{' — ' + detail if detail else ''}")

    price = exchange.fetch_last_price(symbol)
    limits = exchange.market_limits(symbol)
    trigger = price * 0.5
    # La orden debe cumplir la cantidad mínima y también el importe mínimo del par
    # (Bybit EU exige 5 USDC); el importe se mide con holgura al precio de disparo.
    amount = max(float(limits.get("min_amount") or 0) * 2, float(limits.get("min_cost") or 0) * 1.5 / trigger)
    print(f"{symbol}: precio {price}, orden de prueba de {amount:.8f} (≈{amount * price:.2f} al precio actual) "
          f"con disparo en {trigger:.6f} (-50%: no se ejecutará)")
    if amount <= 0:
        print("No conozco la cantidad mínima de este par; prueba con otro --symbol")
        sys.exit(1)
    base = symbol.split("/")[0]
    held = float(exchange.fetch_balances_total().get(base, 0.0))
    if exchange.stop_needs_balance and held < amount:
        print(f"\n{config.exchange_name} solo acepta la orden de stop si tienes la moneda: hacen falta al menos "
              f"{amount:.8f} {base} (≈{amount * price:.2f}) y tienes {held:.8f}.")
        print(f"Compra un poco más de esa cantidad de {base} en {config.exchange_name} (la comisión de compra se cobra "
              f"en {base}) y repite; o usa --symbol con una moneda que ya tengas.")
        sys.exit(1)

    client_id = CLIENT_PREFIX + "verify" + uuid.uuid4().hex[:16]            # 28 caracteres, sin guiones
    order_id = None
    try:
        order = exchange.create_stop_sell(symbol, amount, trigger, client_id)
        order_id = str(order["id"]) if order.get("id") else None
        step("crear la orden de stop", bool(order_id), f"id {order_id}, disparo {order['trigger_price']}, cantidad {order['amount']}")
        if not order_id:
            return
        if held > 0:
            time.sleep(1.0)
            free = float(exchange.fetch_balance(base))
            locked = held - free
            print(f"  [INFO] saldo de {base}: total {held:.8f}, libre con la orden viva {free:.8f}"
                  + (f" -> el exchange BLOQUEA {locked:.8f} mientras vive la orden" if locked > amount * 0.5 else " -> no lo bloquea"))

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
                print(f"  ATENCIÓN: no pude retirar la orden de prueba {order_id}: {exc}. Cancélala a mano en {config.exchange_name}.")

    print("\nRESULTADO: " + ("todo correcto; se puede activar engine.exchange_stops" if ok else "hay fallos; NO actives engine.exchange_stops y pásame esta salida"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
