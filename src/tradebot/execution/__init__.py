"""Capa de ejecución de órdenes: simulada (paper) o real (live)."""

from __future__ import annotations

from ..config import Config
from ..exchange import Exchange
from .base import ExecutionEngine
from .live import LiveExecutionEngine
from .paper import PaperExecutionEngine


def build_execution_engine(config: Config, exchange: Exchange) -> ExecutionEngine:
    if config.mode == "live":
        return LiveExecutionEngine(config, exchange)
    return PaperExecutionEngine(config)


__all__ = [
    "ExecutionEngine",
    "PaperExecutionEngine",
    "LiveExecutionEngine",
    "build_execution_engine",
]
