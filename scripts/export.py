"""Exporta las operaciones cerradas persistidas a un CSV.

Uso:
    python scripts/export.py                         # BD de config.yaml -> data/closed_trades.csv
    python scripts/export.py data/backtest.db        # una BD concreta
    python scripts/export.py -o salida.csv           # otro fichero de salida
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:  # que los acentos se vean bien en la consola de Windows
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.config import load_config  # noqa: E402
from tradebot.reporting import export_trades_csv  # noqa: E402
from tradebot.storage import Storage  # noqa: E402

DEFAULT_OUTPUT = "data/closed_trades.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporta las operaciones cerradas a CSV")
    parser.add_argument("db_path", nargs="?", default=None, help="Ruta a la base de datos (opcional)")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT, help=f"Fichero CSV de salida (def: {DEFAULT_OUTPUT})")
    args = parser.parse_args()

    db_path = args.db_path or load_config().effective_db_path()
    if not Path(db_path).exists():
        print(f"No existe la base de datos: {db_path}")
        return
    storage = Storage(db_path)
    n = export_trades_csv(storage, args.output)
    storage.close()
    print(f"{n} operaciones exportadas de {db_path} a {args.output}")


if __name__ == "__main__":
    main()
