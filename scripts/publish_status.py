"""Publica el status del bot en un GIST SECRETO de GitHub (para leerlo desde
fuera). Corre APARTE del bot (systemd timer / cron): lee los JSON locales que el
bot deja en data/ y los sube. Si GitHub falla, el bot ni se entera.

Requisitos en .env:
  GITHUB_TOKEN=...            # token con scope 'gist' (solo eso)
  TRADEBOT_GIST_ID=...        # opcional; si falta, se CREA el gist y se imprime

Uso:
    python scripts/publish_status.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv  # noqa: E402

from tradebot.publisher import publish_to_gist  # noqa: E402
from tradebot.status import load_merged  # noqa: E402


def main() -> None:
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        print("Falta GITHUB_TOKEN en .env (crea un token con scope 'gist').")
        sys.exit(1)

    try:
        status = load_merged()
    except FileNotFoundError:
        print("No existe data/status.json todavía. Arranca el bot y espera un informe.")
        sys.exit(1)

    gist_id = os.getenv("TRADEBOT_GIST_ID", "").strip() or None
    try:
        res = publish_to_gist(status, token, gist_id)
    except urllib.error.HTTPError as e:
        print(f"Error de la API de GitHub: {e.code} {e.reason}\n{e.read().decode()[:300]}")
        sys.exit(2)

    print(f"Status publicado (gist {res['id']}).")
    print(f"URL raw (pásamela para que la lea):\n  {res['raw_url']}")
    if res["created"]:
        print(f"\n>>> Añade esto a .env para ACTUALIZAR siempre el mismo gist:\n"
              f"    TRADEBOT_GIST_ID={res['id']}")


if __name__ == "__main__":
    main()
