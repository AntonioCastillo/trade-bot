import os
import json
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("GITHUB_TOKEN", "").strip()
gist_id = os.getenv("TRADEBOT_GIST_ID", "").strip()

if not gist_id and Path("data/.gist_id").exists():
    gist_id = Path("data/.gist_id").read_text(encoding="utf-8").strip()

if not gist_id:
    # Try to find the tradebot gist from the user's gists list
    if token:
        req = urllib.request.Request("https://api.github.com/gists")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("User-Agent", "tradebot-status-reader")
        try:
            with urllib.request.urlopen(req) as resp:
                gists = json.loads(resp.read().decode("utf-8"))
                for g in gists:
                    desc = (g.get("description") or "").lower()
                    files = g.get("files", {})
                    if "tradebot" in desc or "status.json" in files or "report.txt" in files:
                        gist_id = g["id"]
                        break
        except Exception as e:
            print(f"Error buscando gists: {e}")

if not gist_id:
    print("NO_GIST_FOUND")
    sys.exit(0)

url = f"https://api.github.com/gists/{gist_id}"
req = urllib.request.Request(url)
if token:
    req.add_header("Authorization", f"Bearer {token}")
req.add_header("User-Agent", "tradebot-status-reader")

try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print(f"GIST_ID: {gist_id}")
        print(f"UPDATED_AT: {data.get('updated_at')}")
        print(f"DESCRIPTION: {data.get('description')}")
        for fname, fobj in data.get("files", {}).items():
            print(f"\n==================== FILE: {fname} ====================")
            print(fobj.get("content", "(empty)"))
except Exception as e:
    print(f"Error leyendo el gist: {e}")
