"""Preflight del carry en REAL (solo-lectura, CERO órdenes).

Comprueba, antes de la primera corrida con dinero de verdad, que todo está en su
sitio:
  - claves con acceso a SPOT y a FUTUROS (firma correcta),
  - USDT en AMBOS monederos (spot para el largo, futuros para el margen del corto),
  - por cada símbolo del carry: contrato del perp, precio, funding actual y el
    sizing que usaría (contratos, notional real) con el tope configurado,
  - veredicto GO / NO-GO.

No envía NADA. Uso:
    python scripts/carry_preflight.py
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.carry import annualized_pct  # noqa: E402
from tradebot.config import load_config  # noqa: E402
from tradebot.exchange import Exchange  # noqa: E402
from tradebot.execution.futures import FuturesBroker  # noqa: E402
from tradebot.factory import setup_logging  # noqa: E402

OK, BAD, WARN = "✅", "❌", "⚠️"


def main() -> None:
    config = load_config()
    setup_logging("WARNING")
    cfg = config.carry
    symbols = cfg.symbols or ["ETH/USDT", "XRP/USDT", "DOGE/USDT"]

    print("=" * 72)
    print("PREFLIGHT CARRY (solo-lectura, no envía órdenes)")
    print("=" * 72)

    problems: list[str] = []

    # 0) Credenciales presentes.
    if not config.credentials.is_complete:
        print(f"{BAD} Faltan claves KuCoin en .env (KUCOIN_API_KEY/SECRET/PASSPHRASE).")
        print("   Sin claves no puedo comprobar los monederos. Aborto.")
        sys.exit(1)
    print(f"{OK} Credenciales presentes en .env")

    # 1) Saldo SPOT (para la pata larga).
    spot = Exchange(config)
    spot_free = 0.0
    try:
        spot_free = spot.fetch_balance("USDT")
        mark = OK if spot_free > 0 else WARN
        print(f"{mark} Monedero SPOT: {spot_free:.2f} USDT libres")
        if spot_free <= 0:
            problems.append("sin USDT en spot (pata larga)")
    except Exception as e:
        print(f"{BAD} No pude leer el saldo SPOT: {type(e).__name__}: {e}")
        problems.append("acceso spot falló (¿permiso Spot?)")

    # 2) Saldo FUTUROS (margen de la pata corta) + prueba de firma en futuros.
    broker = FuturesBroker(config, leverage=cfg.leverage, dry_run=True)
    fut_free = 0.0
    try:
        bal = broker._c().fetch_balance()   # llamada privada: valida permiso de futuros
        fut_free = float((bal.get("free") or {}).get("USDT", 0.0))
        mark = OK if fut_free > 0 else WARN
        print(f"{mark} Monedero FUTUROS: {fut_free:.2f} USDT libres")
        if fut_free <= 0:
            problems.append("sin USDT en futuros (margen del corto): transfiere en KuCoin")
    except Exception as e:
        print(f"{BAD} No pude leer el saldo de FUTUROS: {type(e).__name__}: {e}")
        print("   Suele ser permiso 'Futures Trading' NO activado en la clave.")
        problems.append("acceso futuros falló (¿permiso Futures?)")

    # 3) Sizing por símbolo.
    print("-" * 72)
    print(f"Tope {cfg.max_notional_usdt:.0f} USDT/pos | apalancamiento {cfg.leverage:g}x | "
          f"umbral entrada {cfg.min_annualized_pct:.1f}% anual")
    print(f"{'símbolo':12} {'precio':>10} {'min 1 contr.':>12} {'contr.':>7} "
          f"{'notional':>9} {'funding%':>9}")
    print("-" * 72)
    tradable = 0
    by_pct = spot_free * cfg.notional_pct
    margin_room = fut_free * cfg.leverage
    notional_cap = min(cfg.max_notional_usdt, by_pct or cfg.max_notional_usdt,
                       margin_room or cfg.max_notional_usdt)
    for sym in symbols:
        perp = sym + ":USDT"
        try:
            price = broker.fetch_last_price(perp)
            min1c = broker.notional_of(perp, 1, price)   # USDT que cuesta 1 contrato
            contracts = broker.contracts_for_notional(perp, notional_cap, price)
            real_notional = broker.notional_of(perp, contracts, price)
            fh = spot.fetch_funding_history(perp, 3)
            ann = annualized_pct(float(fh[-1]["fundingRate"])) if fh else float("nan")
            mark = OK if contracts >= 1 else WARN
            print(f"{mark} {sym:10} {price:>10.5f} {min1c:>12.2f} {contracts:>7.0f} "
                  f"{real_notional:>8.2f} {ann:>+8.1f}")
            if contracts >= 1:
                tradable += 1
        except Exception as e:
            print(f"{BAD} {sym:10} error: {type(e).__name__}: {e}")

    if tradable == 0:
        problems.append("ningún símbolo llega a 1 contrato con el tope/saldo actual")

    # 4) Veredicto.
    print("=" * 72)
    if problems:
        print(f"{BAD} NO-GO. Resuelve antes de operar en real:")
        for p in problems:
            print(f"     - {p}")
        print("\nRecuerda: en mode:live el carry va REAL solo; para ENVIAR órdenes de")
        print('           verdad, exporta TRADEBOT_CARRY_LIVE_CONFIRM="SI FUTUROS REAL"')
        sys.exit(2)
    print(f"{OK} GO. Saldos y acceso correctos; {tradable}/{len(symbols)} símbolos operables.")
    print("   Estreno recomendado: arranca SIN la variable de confirmación (DRY-RUN),")
    print("   revisa en el log las órdenes que registraría, y solo entonces exporta")
    print('   TRADEBOT_CARRY_LIVE_CONFIRM="SI FUTUROS REAL".')


if __name__ == "__main__":
    main()
