"""Comisión que paga TU cuenta en cada par de la configuración. No opera.

Sirve para confirmar la comisión real antes de elegir exchange: en Bybit EU resultó ser
el 0,25% aunque su API pública dijera 0,10%, y en OKX Europa depende de tener abierta la
cuenta de derivados X-Perps (0,10% con ella, 0,20% sin ella, según su tabla).

Uso (en el VPS, con las claves del exchange en .env):
    python scripts/check_fees.py --config config.okx.yaml
    python scripts/check_fees.py --config config.bybiteu.yaml --exchange myokx
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

# Comisión a mercado (la que paga el bot) en los exchanges ya comprobados, para comparar.
REFERENCE = {"KuCoin (el de siempre)": 0.0010, "Bybit EU (comprobado el 2026-10-14)": 0.0025}


def summarize(fees: dict[str, dict[str, float]], expected: float) -> list[str]:
    """Líneas de resumen a partir de {par: {'taker', 'maker'}}."""
    takers = sorted({round(f["taker"], 6) for f in fees.values()})
    lines = []
    if len(takers) == 1:
        lines.append(f"Todos los pares pagan lo mismo a mercado: {takers[0] * 100:.3f}%")
    else:
        lines.append(f"La comisión a mercado varía por par: de {takers[0] * 100:.3f}% a {takers[-1] * 100:.3f}%")
    worst = max(f["taker"] for f in fees.values())
    for name, ref in REFERENCE.items():
        word = "menos" if worst < ref - 1e-9 else ("lo mismo" if abs(worst - ref) < 1e-9 else "más")
        lines.append(f"  frente a {name}, {ref * 100:.2f}%: {word}")
    if worst <= expected + 1e-9:
        lines.append(f"RESULTADO: comisión igual o menor que la de la configuración ({expected * 100:.3f}%)")
    else:
        lines.append(f"RESULTADO: comisión MAYOR que la de la configuración ({expected * 100:.3f}%); "
                     "las simulaciones con esa configuración serían optimistas")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Comisión real de la cuenta por par (no opera)")
    parser.add_argument("--config", default="config.yaml", help="Fichero de configuración (def: config.yaml)")
    parser.add_argument("--exchange", default=None, help="Otro exchange con la misma configuración (p. ej. myokx)")
    args = parser.parse_args()

    config = load_config(args.config, require_credentials=False, exchange=args.exchange)
    if not config.credentials.is_complete:
        print(f"Faltan las claves de {config.exchange_name} en .env ({', '.join(credential_env_names(config.exchange))})")
        sys.exit(1)
    exchange = Exchange(config)
    print(f"{config.exchange_name}: comisión de tu cuenta en los {len(config.symbols())} pares de {args.config}\n")
    fees: dict[str, dict[str, float]] = {}
    for symbol in config.symbols():
        try:
            fees[symbol] = exchange.fetch_trading_fee(symbol)
            f = fees[symbol]
            print(f"  {symbol:10} a mercado {f['taker'] * 100:.3f}%   orden limitada {f['maker'] * 100:.3f}%")
        except Exception as exc:
            print(f"  {symbol:10} no pude leerla: {type(exc).__name__}: {exc}")
    if not fees:
        print("\nRESULTADO: no pude leer ninguna comisión; pásame esta salida")
        sys.exit(1)
    print()
    for line in summarize(fees, config.engine.fee_pct):
        print(line)


if __name__ == "__main__":
    main()
