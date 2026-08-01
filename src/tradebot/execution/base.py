"""Interfaz de la capa de ejecución."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Fill, Order


class OrderRejected(Exception):
    """La orden no se pudo ejecutar (tamaño mínimo, precisión, saldo, etc.).

    No es un fallo fatal: el motor la registra y sigue operando."""


class ExecutionEngine(ABC):
    @abstractmethod
    def execute(self, order: Order) -> Fill:
        """Ejecuta una orden y devuelve el Fill resultante."""
        raise NotImplementedError

    @abstractmethod
    def get_balance(self) -> float:
        """Saldo disponible en la moneda de cotización (p.ej. USDT)."""
        raise NotImplementedError
