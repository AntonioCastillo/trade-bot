"""Consulta e imprime el informe de operaciones persistidas.

Uso:
    python scripts/report.py                    # lee la BD de config.yaml
    python scripts/report.py data/backtest.db   # lee una BD concreta
"""

from __future__ import annotations

import sys
from pathlib import Path

try:  # que los acentos se vean bien en la consola de Windows
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.config import load_config  # noqa: E402
from tradebot.reporting import render_report  # noqa: E402
from tradebot.storage import Storage  # noqa: E402


def main() -> None:
    config = load_config()
    db_path = sys.argv[1] if len(sys.argv) > 1 else config.db_path
    if not Path(db_path).exists():
        print(f"No existe la base de datos: {db_path}")
        print("Ejecuta antes una simulación (scripts/backtest.py o scripts/run.py).")
        return
    storage = Storage(db_path)
    print(render_report(storage, quote=config.risk.quote_currency,
                        starting_balance=config.risk.starting_balance))
    storage.close()


if __name__ == "__main__":
    main()
