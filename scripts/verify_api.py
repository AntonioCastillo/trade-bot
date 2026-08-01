"""Verifica la API real de KuCoin con una operación de ida y vuelta de ~1 USD.

Uso:
    python scripts/verify_api.py             # 1 USD en BTC/USDT
    python scripts/verify_api.py 1 XRP/USDT  # importe y símbolo

Sin claves en .env, o sin confirmar, funciona en DRY-RUN (no opera): solo
muestra el plan y comprueba precio, mínimo y saldo. Para ejecutar de verdad
necesitas claves válidas y escribir la confirmación exacta.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.config import load_config  # noqa: E402
from tradebot.exchange import Exchange  # noqa: E402
from tradebot.factory import setup_logging  # noqa: E402
from tradebot.notifier import build_notifier  # noqa: E402
from tradebot.selfcheck import run_api_check  # noqa: E402


def main() -> None:
    usd = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    symbol = sys.argv[2] if len(sys.argv) > 2 else "BTC/USDT"

    config = load_config()
    setup_logging(config.log_level)
    exchange = Exchange(config)

    price = exchange.fetch_last_price(symbol)          # público, no opera
    limits = exchange.market_limits(symbol)
    print("=" * 60)
    print("VERIFICACIÓN DE API — plan")
    print("=" * 60)
    print(f"Símbolo:        {symbol}")
    print(f"Precio actual:  {price}")
    print(f"Importe:        {usd} {config.risk.quote_currency}")
    print(f"Mínimo KuCoin:  {limits.get('min_cost')} {config.risk.quote_currency}")
    print("Acción:         COMPRA a mercado + VENTA inmediata (round-trip real)")
    print("=" * 60)

    if not config.credentials.is_complete:
        print("\nDRY-RUN: faltan claves en .env (KUCOIN_API_KEY/SECRET/PASSPHRASE).")
        print("Rellénalas para poder ejecutar la verificación real.")
        return

    min_cost = limits.get("min_cost")
    if min_cost and usd < min_cost:
        print(f"\nEl importe {usd} está por debajo del mínimo {min_cost}. Sube el importe.")
        return

    print("\n*** Esto ejecuta una COMPRA y VENTA REALES por ~%.2f %s. ***"
          % (usd, config.risk.quote_currency))
    if input("Escribe 'VERIFICAR API REAL' para continuar: ").strip() != "VERIFICAR API REAL":
        print("Cancelado (no se ha operado).")
        return

    notifier = build_notifier(
        config.credentials.telegram_token, config.credentials.telegram_chat_id
    )
    result = run_api_check(exchange, symbol, usd, config.risk.quote_currency, notifier)

    # Marca la API como verificada para que el bot no repita el chequeo al arrancar.
    from tradebot.daemon import API_CHECK_MARKER  # noqa: E402
    import datetime as _dt
    marker = Path(API_CHECK_MARKER)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(_dt.datetime.now(_dt.timezone.utc).isoformat(), encoding="utf-8")

    print("\n===== RESULTADO =====")
    print(f"Cantidad comprada: {result.amount:.8f}")
    print(f"Precio compra:     {result.buy_price:.6f}")
    print(f"Precio venta:      {result.sell_price:.6f}")
    print(f"Coste validación:  {result.net:+.4f} {config.risk.quote_currency}")
    print("API verificada correctamente. ✅")


if __name__ == "__main__":
    main()
