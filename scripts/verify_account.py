"""Comprueba la cuenta del exchange configurado SIN operar: pares, mínimos, saldo y comisión.

Es el primer paso al estrenar un exchange (o unas claves nuevas): no envía ninguna
orden. Después vienen `verify-api` (compra y venta real de ~1) y `verify-stops`.

Uso:
    python scripts/verify_account.py                              # config.yaml
    python scripts/verify_account.py --config otra_config.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.config import credential_env_names, load_config  # noqa: E402
from tradebot.exchange import Exchange  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Comprueba la cuenta del exchange sin operar")
    parser.add_argument("--config", default="config.yaml", help="Fichero de configuración (def: config.yaml)")
    parser.add_argument("--exchange", default=None, help="Otro exchange con la misma configuración (p. ej. myokx)")
    args = parser.parse_args()

    config = load_config(args.config, require_credentials=False, exchange=args.exchange)
    quote = config.risk.quote_currency
    exchange = Exchange(config)
    ok = True

    def step(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and passed
        print(f"  [{'OK' if passed else 'FALLO'}] {name}{' — ' + detail if detail else ''}")

    print(f"{config.exchange_name} | moneda de cotización {quote} | {len(config.instruments)} pares en {args.config}")

    print("\nDatos públicos:")
    try:
        available = exchange.market_symbols()
        missing = [s for s in config.symbols() if s not in available]
        step("todos los pares de la configuración existen", not missing, "faltan " + ", ".join(missing) if missing else "")
    except Exception as exc:
        step("cargar los mercados", False, f"{type(exc).__name__}: {exc}")
        available = set()
    try:
        price = exchange.fetch_last_price(config.reference_symbol)
        step(f"precio de {config.reference_symbol}", price > 0, str(price))
    except Exception as exc:
        step(f"precio de {config.reference_symbol}", False, f"{type(exc).__name__}: {exc}")
    source = (f"{config.data_exchange} ({config.data_symbol(config.reference_symbol)})"
              if config.signals_elsewhere else config.exchange_name)
    try:
        candles = exchange.fetch_ohlcv(config.reference_symbol, "1d", limit=config.lookback)
        step(f"velas de las señales: {source}", len(candles) > 50, f"{len(candles)} velas diarias")
    except Exception as exc:
        step(f"velas de las señales: {source}", False, f"{type(exc).__name__}: {exc}")
    for symbol in config.symbols():
        if symbol not in available:
            continue
        try:
            limits = exchange.market_limits(symbol)
            print(f"       {symbol:12} mínimo por orden: {limits.get('min_cost')} {quote} / {limits.get('min_amount')} {symbol.split('/')[0]}")
        except Exception as exc:
            step(f"límites de {symbol}", False, f"{type(exc).__name__}: {exc}")

    print("\nCuenta:")
    if not config.credentials.is_complete:
        print(f"  Sin claves en .env ({', '.join(credential_env_names(config.exchange))}): no compruebo la cuenta.")
        print("\nRESULTADO: " + ("datos públicos correctos; faltan las claves para comprobar la cuenta" if ok else "hay fallos; pásame esta salida"))
        sys.exit(0 if ok else 1)
    try:
        free = exchange.fetch_balance(quote)
        step(f"leer el saldo libre de {quote}", True, f"{free:.2f} {quote}")
    except Exception as exc:
        step(f"leer el saldo libre de {quote}", False, f"{type(exc).__name__}: {exc}")
    try:
        totals = exchange.fetch_balances_total()
        step("leer el saldo total por moneda", True, ", ".join(f"{k} {v:g}" for k, v in sorted(totals.items())) or "cuenta vacía")
    except Exception as exc:
        step("leer el saldo total por moneda", False, f"{type(exc).__name__}: {exc}")
    try:
        fee = exchange.fetch_trading_fee(config.reference_symbol)
        expected = config.engine.fee_pct
        detail = f"compra/venta a mercado {fee['taker'] * 100:.3f}%, orden limitada {fee['maker'] * 100:.3f}%"
        if fee["taker"] > expected + 1e-9:
            detail += f" — MÁS que el {expected * 100:.3f}% con el que se han hecho las simulaciones"
        step("leer la comisión de la cuenta", fee["taker"] <= expected + 1e-9, detail)
    except Exception as exc:
        step("leer la comisión de la cuenta", False, f"{type(exc).__name__}: {exc}")
    try:
        orders = exchange.fetch_open_stop_orders()
        step("listar las órdenes de stop", True, f"{len(orders)} vivas")
    except Exception as exc:
        step("listar las órdenes de stop", False, f"{type(exc).__name__}: {exc}")

    print("\nRESULTADO: " + ("todo correcto; siguiente paso: verify-api y verify-stops" if ok else "hay fallos; pásame esta salida"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
