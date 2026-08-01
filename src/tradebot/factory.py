"""Ensambla todas las piezas del bot a partir de la configuración."""

from __future__ import annotations

import logging
from pathlib import Path

from .config import Config, load_config
from .engine import Engine
from .exchange import Exchange
from .execution import build_execution_engine
from .notifier import PrefixNotifier, build_notifier
from .risk import RiskManager
from .storage import Storage
from .strategy import Strategy, build_strategy


def setup_logging(level: str, log_file: str | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        handlers=handlers,
        force=True,  # permite reconfigurar si ya había logging
    )


def build_strategies(config: Config) -> dict[str, Strategy]:
    """Una instancia de estrategia por símbolo, según su categoría."""
    return {
        ins.symbol: build_strategy(ins.strategy_name, ins.strategy_params)
        for ins in config.instruments
    }


def build_engine(config: Config | None = None, log_file: str | None = None) -> Engine:
    config = config or load_config()
    setup_logging(config.log_level, log_file=log_file)

    exchange = Exchange(config)
    strategies = build_strategies(config)
    risk = RiskManager(config.risk)
    risk.reset_day(config.risk.starting_balance)
    execution = build_execution_engine(config, exchange)
    storage = Storage(config.db_path)
    tag = "🔴 [REAL]" if config.mode == "live" else "🧪 [SIMULACIÓN]"
    notifier = PrefixNotifier(
        build_notifier(config.credentials.telegram_token,
                       config.credentials.telegram_chat_id),
        tag,
    )

    return Engine(config, strategies, risk, execution, storage,
                  exchange=exchange, notifier=notifier, head_log_dir="logs/heads")
