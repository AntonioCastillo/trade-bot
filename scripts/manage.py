#!/usr/bin/env python3
"""CLI Unificada de Gestión para TradeBot.

Permite ejecutar todas las tareas operativas y de mantenimiento desde un único comando.

Uso:
    python scripts/manage.py status [--gist]
    python scripts/manage.py sync-funding
    python scripts/manage.py close-carry [--dry-run]
    python scripts/manage.py report [db_path]
    python scripts/manage.py verify-api [--usd USD] [--symbol SYMBOL]
    python scripts/manage.py backtest [--limit N] [--config PATH]
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


def cmd_status(args: argparse.Namespace) -> None:
    from beneficios import main as beneficios_main
    # Forward arguments appropriately
    sys.argv = [sys.argv[0]]
    if args.gist:
        sys.argv.append("--gist")
    beneficios_main()


def cmd_sync_funding(args: argparse.Namespace) -> None:
    from sync_funding import main as sync_main
    sys.argv = [sys.argv[0]]
    sync_main()


def cmd_close_carry(args: argparse.Namespace) -> None:
    from close_carry import main as close_main
    sys.argv = [sys.argv[0]]
    if args.dry_run:
        sys.argv.append("--dry-run")
    close_main()


def cmd_report(args: argparse.Namespace) -> None:
    from report import main as report_main
    sys.argv = [sys.argv[0]]
    if args.db_path:
        sys.argv.append(args.db_path)
    report_main()


def cmd_verify_api(args: argparse.Namespace) -> None:
    from verify_api import main as verify_main
    sys.argv = [sys.argv[0], str(args.usd), args.symbol]
    verify_main()


def cmd_backtest(args: argparse.Namespace) -> None:
    from backtest import main as backtest_main
    sys.argv = [sys.argv[0], str(args.limit), args.config]
    backtest_main()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="Panel de Control y CLI Unificada de TradeBot",
    )
    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    # status
    p_status = subparsers.add_parser("status", help="Muestra el estado y balance consolidado")
    p_status.add_argument("--gist", action="store_true", help="Consulta el último estado en vivo desde GitHub Gist")
    p_status.set_defaults(func=cmd_status)

    # sync-funding
    p_sync = subparsers.add_parser("sync-funding", help="Sincroniza el historial de funding real de KuCoin a SQLite")
    p_sync.set_defaults(func=cmd_sync_funding)

    # close-carry
    p_close = subparsers.add_parser("close-carry", help="Cierra y desmantela las posiciones de Carry Trade de forma segura")
    p_close.add_argument("--dry-run", action="store_true", help="Modo simulación (auditoría sin enviar órdenes)")
    p_close.set_defaults(func=cmd_close_carry)

    # report
    p_rep = subparsers.add_parser("report", help="Genera el informe de rendimiento histórico")
    p_rep.add_argument("db_path", nargs="?", default=None, help="Ruta a la base de datos (opcional)")
    p_rep.set_defaults(func=cmd_report)

    # verify-api
    p_ver = subparsers.add_parser("verify-api", help="Verifica las credenciales API con una micro-orden de prueba")
    p_ver.add_argument("--usd", type=float, default=1.0, help="Importe en USD (def: 1.0)")
    p_ver.add_argument("--symbol", type=str, default="BTC/USDT", help="Símbolo a usar (def: BTC/USDT)")
    p_ver.set_defaults(func=cmd_verify_api)

    # backtest
    p_bt = subparsers.add_parser("backtest", help="Ejecuta backtesting sobre histórico")
    p_bt.add_argument("--limit", type=int, default=1000, help="Número de velas a evaluar")
    p_bt.add_argument("--config", type=str, default="config.yaml", help="Fichero de configuración")
    p_bt.set_defaults(func=cmd_backtest)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
