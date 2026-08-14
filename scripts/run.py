"""Punto de entrada ÚNICO del bot autónomo y desatendido.

Uso:
    python scripts/run.py

Recorre todo el universo en bucle sin intervención: opera (en simulación),
persiste cada operación, reinicia el cortafuegos diario y vuelca un informe a
data/report.txt cada cierto tiempo. Se detiene con Ctrl+C.

Por seguridad arranca en modo paper salvo que config.yaml tenga mode: live Y
haya credenciales en .env.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:  # acentos correctos en la consola de Windows
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv  # noqa: E402
from tradebot.config import load_config  # noqa: E402
from tradebot.daemon import run_forever  # noqa: E402
from tradebot.notifier import PrefixNotifier, build_notifier  # noqa: E402

CONFIRM = "SI OPERAR EN REAL"


def main() -> None:
    load_dotenv()
    config_path = "config.yaml"
    
    # Leer el modo desde la variable de entorno MODO o TRADEBOT_MODO (para entornos sin consola/VPS)
    env_modo = os.environ.get("MODO", os.environ.get("TRADEBOT_MODO", "")).strip().lower()
    if env_modo in ("futuros", "futures"):
        config_path = "config_futures.yaml"
        print(">>> [ENV] Cargando configuración de FUTUROS (config_futures.yaml)")
    elif env_modo == "spot":
        config_path = "config.yaml"
        print(">>> [ENV] Cargando configuración de SPOT (config.yaml)")

    # Los argumentos por línea de comandos tienen prioridad sobre la variable de entorno
    if len(sys.argv) > 1:
        if "futures" in sys.argv or "futuros" in sys.argv:
            config_path = "config_futures.yaml"
            print(">>> [ARG] Cargando configuración de FUTUROS (config_futures.yaml)")
        elif "spot" in sys.argv:
            config_path = "config.yaml"
            print(">>> [ARG] Cargando configuración de SPOT (config.yaml)")
        else:
            # Comprobar si se ha pasado un archivo .yaml personalizado
            for arg in sys.argv[1:]:
                if arg.endswith(".yaml") and Path(arg).exists():
                    config_path = arg
                    print(f">>> [ARG] Cargando configuración personalizada: {config_path}")
                    break

    config = load_config(config_path)

    # Confirmación para operar en real. En terminal interactiva se pregunta; en
    # headless (systemd/VPS) se usa la variable de entorno TRADEBOT_LIVE_CONFIRM.
    respuesta = os.environ.get("TRADEBOT_LIVE_CONFIRM", "").strip()
    if not respuesta and sys.stdin.isatty():
        print("=" * 60)
        print(f"Para operar en REAL escribe exactamente:  {CONFIRM}")
        print("Cualquier otra cosa (o Enter) = MODO PAPER (simulación, sin dinero)")
        print("=" * 60)
        try:
            respuesta = input("> ").strip()
        except EOFError:
            respuesta = ""

    if respuesta == CONFIRM and config.credentials.is_complete:
        config.mode = "live"
        print(">>> MODO REAL: se operará con DINERO DE VERDAD.")
    else:
        if respuesta == CONFIRM:
            print("Faltan claves API completas -> arranco en PAPER por seguridad.")
        config.mode = "paper"
        print(">>> MODO PAPER (simulación, sin dinero real).")

    tag = "🔴 [REAL]" if config.mode == "live" else "🧪 [SIMULACIÓN]"
    try:
        run_forever(config)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        # Caída total: avisa por Telegram antes de morir (el .bat reinicia).
        PrefixNotifier(
            build_notifier(config.credentials.telegram_token,
                           config.credentials.telegram_chat_id),
            tag,
        ).notify(
            f"🛑 <b>Bot CAÍDO</b>\n{type(e).__name__}: {e}\n"
            "Se reiniciará automáticamente."
        )
        raise


if __name__ == "__main__":
    main()
