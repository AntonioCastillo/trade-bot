"""Sniper de recién listadas (EXPERIMENTAL — ALTO RIESGO).

Uso:
    python scripts/sniper.py

Requiere `sniper.enabled: true` en config.yaml. Detecta nuevos pares */USDT en
KuCoin y entra fuerte buscando el pump inicial. En modo live opera con dinero
REAL. Se detiene con Ctrl+C.

AVISO: esto NO es validable con backtesting y es más apostar que invertir.
Úsalo solo con capital que puedas perder por completo.
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
from tradebot.sniper import Sniper  # noqa: E402


def main() -> None:
    config = load_config()
    setup_logging(config.log_level, log_file="logs/sniper.log")

    if not config.sniper.enabled:
        print("El sniper está desactivado. Pon 'sniper: { enabled: true }' en config.yaml.")
        return

    live = config.mode == "live"
    if live:
        print("*** ATENCION: SNIPER en modo LIVE — dinero REAL en monedas recién listadas. ***")
        print("*** Es la operativa de MAYOR riesgo del bot. ***")
        if input("Escribe 'SNIPE REAL' para continuar: ").strip() != "SNIPE REAL":
            print("Cancelado.")
            return

    exchange = Exchange(config)
    notifier = build_notifier(
        config.credentials.telegram_token, config.credentials.telegram_chat_id
    )
    Sniper(config, exchange, notifier, live=live).run_forever()


if __name__ == "__main__":
    main()
