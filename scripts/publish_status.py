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

from tradebot.status import load_merged  # noqa: E402

API = "https://api.github.com"
FILENAME = "tradebot_status.json"


def _req(url: str, token: str, method: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "tradebot-status")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


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

    content = json.dumps(status, indent=2, ensure_ascii=False)
    files = {"files": {FILENAME: {"content": content}}}
    gist_id = os.getenv("TRADEBOT_GIST_ID", "").strip()

    try:
        if gist_id:
            resp = _req(f"{API}/gists/{gist_id}", token, "PATCH", files)
        else:
            resp = _req(f"{API}/gists", token, "POST",
                        {"description": "tradebot status (secreto)", "public": False, **files})
    except urllib.error.HTTPError as e:
        print(f"Error de la API de GitHub: {e.code} {e.reason}\n{e.read().decode()[:300]}")
        sys.exit(2)

    gid = resp["id"]
    login = resp["owner"]["login"]
    raw = f"https://gist.githubusercontent.com/{login}/{gid}/raw/{FILENAME}"
    print(f"Status publicado (gist {gid}).")
    print(f"URL raw (pásamela para que la lea):\n  {raw}")
    if not gist_id:
        print(f"\n>>> Añade esto a .env para ACTUALIZAR siempre el mismo gist:\n"
              f"    TRADEBOT_GIST_ID={gid}")


if __name__ == "__main__":
    main()
