"""Subida del status a un GIST SECRETO de GitHub (urllib, sin dependencias).

Lo usan tanto el hilo del daemon (publicación automática) como el script suelto.
"""

from __future__ import annotations

import json
import urllib.request

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


def publish_to_gist(status: dict, token: str, gist_id: str | None = None) -> dict:
    """Crea (si no hay id) o actualiza el gist con el status. Devuelve
    {id, raw_url, created}. La `raw_url` es estable y se lee sin token
    (los gists secretos son no-listados, no privados)."""
    content = json.dumps(status, indent=2, ensure_ascii=False)
    files = {"files": {FILENAME: {"content": content}}}
    if gist_id:
        resp = _req(f"{API}/gists/{gist_id}", token, "PATCH", files)
        created = False
    else:
        resp = _req(f"{API}/gists", token, "POST",
                    {"description": "tradebot status (secreto)", "public": False, **files})
        created = True
    gid = resp["id"]
    login = (resp.get("owner") or {}).get("login", "")
    raw = f"https://gist.githubusercontent.com/{login}/{gid}/raw/{FILENAME}"
    return {"id": gid, "raw_url": raw, "created": created}
