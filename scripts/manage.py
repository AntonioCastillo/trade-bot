#!/usr/bin/env python3
"""CLI Unificada de Gestión para TradeBot.

Permite ejecutar todas las tareas operativas y de mantenimiento desde un único comando.

Uso:
    python scripts/manage.py status [--gist]
    python scripts/manage.py sync-funding
    python scripts/manage.py close-carry [--dry-run]
    python scripts/manage.py report [db_path]
    python scripts/manage.py export [db_path] [-o FILE]
    python scripts/manage.py pause CABEZA [--days N]     # pausa manual (sin --days: hasta reanudar)
    python scripts/manage.py resume CABEZA               # levanta la pausa manual y la de strikes
    python scripts/manage.py pauses                      # qué cabezas están en pausa
    python scripts/manage.py verify-stops [--symbol PAR] # prueba las órdenes de stop contra KuCoin (no opera)
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


def cmd_export(args: argparse.Namespace) -> None:
    from export import main as export_main
    sys.argv = [sys.argv[0]]
    if args.db_path:
        sys.argv.append(args.db_path)
    if args.output:
        sys.argv += ["-o", args.output]
    export_main()


def _pause_context():
    """Config, almacenamiento del bot y lista de cabezas activas."""
    from tradebot.config import load_config
    from tradebot.storage import Storage

    config = load_config()
    db_path = config.effective_db_path()
    if not Path(db_path).exists():
        print(f"No existe la base de datos: {db_path}")
        sys.exit(1)
    heads = list(dict.fromkeys(ins.category for ins in config.instruments))
    return config, Storage(db_path), heads


def _tell_telegram(config, text: str) -> None:
    try:
        from tradebot.notifier import build_notifier
        build_notifier(config.telegram_token, config.telegram_chat_id).notify(text)
    except Exception:
        pass


def _check_head(head: str, heads: list[str]) -> None:
    if head not in heads:
        print(f"Cabeza desconocida: {head}. Activas: {', '.join(heads)}")
        sys.exit(1)


def cmd_pause(args: argparse.Namespace) -> None:
    from tradebot.pause_control import describe_until, pause_head

    config, storage, heads = _pause_context()
    _check_head(args.head, heads)
    until = pause_head(storage, args.head, args.days)
    storage.close()
    print(f"{args.head}: en pausa manual {describe_until(until)}.")
    print("No abrirá posiciones nuevas; las abiertas se siguen gestionando. Surte efecto sin reiniciar.")
    _tell_telegram(config, f"⏸️ <b>Pausa manual</b>: {args.head}\n{describe_until(until).capitalize()}. "
                           "Las posiciones abiertas se siguen gestionando.")


def cmd_resume(args: argparse.Namespace) -> None:
    from tradebot.pause_control import resume_head

    config, storage, heads = _pause_context()
    _check_head(args.head, heads)
    lifted = resume_head(storage, args.head)
    storage.close()
    if not lifted:
        print(f"{args.head}: no estaba en pausa.")
        return
    print(f"{args.head}: reanudada (pausa levantada: {' y '.join(lifted)}). Surte efecto sin reiniciar.")
    _tell_telegram(config, f"▶️ <b>Cabeza reanudada a mano</b>: {args.head}\nPausa levantada: {' y '.join(lifted)}.")


def cmd_pauses(args: argparse.Namespace) -> None:
    from tradebot.pause_control import active_pauses

    _, storage, heads = _pause_context()
    pauses = active_pauses(storage, heads)
    storage.close()
    for head in heads:
        print(f"{head}: " + ("; ".join(pauses[head]) if head in pauses else "operando"))


def cmd_verify_stops(args: argparse.Namespace) -> None:
    from verify_stops import main as verify_stops_main
    sys.argv = [sys.argv[0], "--symbol", args.symbol]
    verify_stops_main()


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

    # export
    p_exp = subparsers.add_parser("export", help="Exporta las operaciones cerradas a CSV")
    p_exp.add_argument("db_path", nargs="?", default=None, help="Ruta a la base de datos (opcional)")
    p_exp.add_argument("-o", "--output", default=None, help="Fichero CSV de salida (def: data/closed_trades.csv)")
    p_exp.set_defaults(func=cmd_export)

    # pausa manual por cabeza
    p_pause = subparsers.add_parser("pause", help="Pausa a mano una cabeza (solo entradas nuevas)")
    p_pause.add_argument("head", help="Nombre de la cabeza, p. ej. grid_lateral")
    p_pause.add_argument("--days", type=float, default=None, help="Días de pausa (sin indicar: hasta reanudar)")
    p_pause.set_defaults(func=cmd_pause)

    p_resume = subparsers.add_parser("resume", help="Levanta la pausa de una cabeza (manual y por strikes)")
    p_resume.add_argument("head", help="Nombre de la cabeza")
    p_resume.set_defaults(func=cmd_resume)

    p_pauses = subparsers.add_parser("pauses", help="Lista las cabezas en pausa")
    p_pauses.set_defaults(func=cmd_pauses)

    p_vs = subparsers.add_parser("verify-stops", help="Prueba las órdenes de stop contra KuCoin real (no opera)")
    p_vs.add_argument("--symbol", type=str, default="ETH/USDT", help="Par a usar (def: ETH/USDT)")
    p_vs.set_defaults(func=cmd_verify_stops)

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
