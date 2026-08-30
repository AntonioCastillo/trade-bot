"""Funding-rate carry delta-neutral (long spot + short perpetuo).

Idea: comprar spot y cortar el perpetuo del mismo tamaño → cubierto ante el
precio. Cada 8h se cobra (o paga) el funding; el corto lo cobra cuando es
positivo. El resultado ≈ funding acumulado ± basis (divergencia spot/perp).

Este módulo lleva la CONTABILIDAD (paper) y las DECISIONES (abrir si el funding
anualizado supera un mínimo; cerrar si cae por debajo). La ejecución real de
órdenes de futuros se conecta después (necesita API de futuros).

PERIODS_PER_YEAR: funding cada 8h -> 3/día.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .config import CarryConfig, Config
from .exchange import Exchange
from .notifier import Notifier, NullNotifier

logger = logging.getLogger(__name__)

PERIODS_PER_YEAR = 3 * 365


def annualized_pct(rate: float) -> float:
    """Rendimiento anualizado si el funding por periodo se mantuviera."""
    return rate * PERIODS_PER_YEAR * 100


@dataclass
class CarryPosition:
    symbol: str                 # spot, p.ej. ETH/USDT
    notional: float             # USDT por pata
    spot_entry: float
    perp_entry: float
    spot_amount: float
    perp_amount: float
    funding_collected: float = 0.0
    last_funding_ts: int = 0
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def spot_value(self, spot_now: float) -> float:
        return self.spot_amount * spot_now

    def perp_pnl(self, perp_now: float) -> float:
        # Corto: gana si el perp baja respecto a la entrada.
        return (self.perp_entry - perp_now) * self.perp_amount

    def net_pnl(self, spot_now: float, perp_now: float) -> float:
        """P&L neto (sin contar comisiones): (spot - notional) + perp corto + funding."""
        return (self.spot_value(spot_now) - self.notional) + self.perp_pnl(perp_now) + self.funding_collected


class CarryManager:
    """Gestor del carry en modo PAPER (contabilidad sobre un balance simulado)."""

    def __init__(self, cfg: CarryConfig, starting_balance: float):
        self.cfg = cfg
        self.balance = starting_balance          # efectivo (quote)
        self.positions: dict[str, CarryPosition] = {}

    # --- Decisiones ---------------------------------------------------------------

    def should_open(self, symbol: str, rate: float) -> bool:
        return (symbol not in self.positions
                and annualized_pct(rate) >= self.cfg.min_annualized_pct)

    def should_close(self, symbol: str, rate: float) -> bool:
        return (symbol in self.positions
                and annualized_pct(rate) < self.cfg.exit_annualized_pct)

    # --- Operativa (paper) --------------------------------------------------------

    def open(self, symbol: str, spot_price: float, perp_price: float,
             funding_ts: int = 0) -> CarryPosition:
        notional = self.balance * self.cfg.notional_pct
        spot_amount = notional / spot_price
        perp_amount = notional / perp_price
        fees = notional * self.cfg.fee_pct * 2      # una comisión por pata
        self.balance -= notional + fees             # el spot inmoviliza notional; el perp es margen
        pos = CarryPosition(
            symbol=symbol, notional=notional, spot_entry=spot_price,
            perp_entry=perp_price, spot_amount=spot_amount, perp_amount=perp_amount,
            last_funding_ts=funding_ts,
        )
        self.positions[symbol] = pos
        logger.info("[CARRY] ABRE %s notional %.2f (spot %.6f / perp %.6f) anualizado objetivo",
                    symbol, notional, spot_price, perp_price)
        return pos

    def accrue_funding(self, symbol: str, rate: float, funding_ts: int) -> float:
        """Acumula un nuevo periodo de funding (solo si es posterior al último)."""
        pos = self.positions.get(symbol)
        if pos is None or funding_ts <= pos.last_funding_ts:
            return 0.0
        payment = rate * pos.notional            # el corto cobra si rate>0
        pos.funding_collected += payment
        pos.last_funding_ts = funding_ts
        self.balance += payment
        return payment

    def close(self, symbol: str, spot_price: float, perp_price: float) -> float:
        pos = self.positions.pop(symbol)
        fees = pos.notional * self.cfg.fee_pct * 2
        # Recupera el spot vendido y el P&L del corto; el funding ya está en balance.
        self.balance += pos.spot_value(spot_price) + pos.perp_pnl(perp_price) - fees
        net = pos.net_pnl(spot_price, perp_price) - fees
        logger.info("[CARRY] CIERRA %s | funding %.4f | P&L neto %.4f",
                    symbol, pos.funding_collected, net)
        return net

    def equity(self, prices: dict[str, tuple[float, float]]) -> float:
        """Valor total = efectivo + valor spot + P&L del corto de cada posición.
        `prices[symbol] = (spot_now, perp_now)`."""
        total = self.balance
        for sym, pos in self.positions.items():
            spot_now, perp_now = prices.get(sym, (pos.spot_entry, pos.perp_entry))
            total += pos.spot_value(spot_now) + pos.perp_pnl(perp_now)
        return total


class CarryRunner:
    """Ejecuta el carry en un bucle (PAPER). Pensado para correr en un hilo del
    daemon o suelto. NO ejecuta órdenes reales todavía (la ejecución de futuros
    llegará con las claves); lleva la contabilidad sobre un balance simulado."""

    def __init__(self, config: Config, exchange: Exchange, notifier: Notifier | None = None):
        self.config = config
        self.cfg = config.carry
        self.exchange = exchange
        self.notifier = notifier or NullNotifier()
        self.mgr = self._build_manager()
        self._symbols = self.cfg.symbols or ["ETH/USDT", "XRP/USDT", "DOGE/USDT"]
        self._fut = None

    def _build_manager(self):
        """El MODO manda: en paper todo es paper; en live el carry va REAL.
        Sin doble confirmación: si el bot está en live, el carry también."""
        if self.config.mode != "live":
            return CarryManager(self.cfg, self.config.risk.starting_balance)

        from .carry_live import LiveCarryExecutor
        from .execution.futures import FuturesBroker

        broker = FuturesBroker(self.config, leverage=self.cfg.leverage, dry_run=False)
        logger.warning("[CARRY] ejecutor REAL de futuros | apalancamiento=%sx | "
                       "tope=%.0f USDT/pos", self.cfg.leverage, self.cfg.max_notional_usdt)
        self.notifier.notify(
            f"⚙️ <b>CARRY futuros</b> arrancado en 🔴 REAL "
            f"(lev {self.cfg.leverage:g}x, tope {self.cfg.max_notional_usdt:.0f} USDT/pos)")
        return LiveCarryExecutor(self.config, self.exchange, broker, self.notifier)

    def _futures(self):
        import ccxt
        if self._fut is None:
            self._fut = ccxt.kucoinfutures({"enableRateLimit": True})
        return self._fut

    def cycle(self) -> None:
        prices: dict = {}
        for spot_sym in self._symbols:
            perp_sym = spot_sym + ":USDT"
            try:
                fh = self.exchange.fetch_funding_history(perp_sym, 3)
                rate = float(fh[-1]["fundingRate"])
                fts = int(fh[-1]["timestamp"])
                spot = self.exchange.fetch_last_price(spot_sym)
                perp = float(self._futures().fetch_ticker(perp_sym)["last"])
            except Exception:
                logger.warning("[CARRY] no pude leer datos de %s; lo salto", spot_sym)
                continue
            prices[spot_sym] = (spot, perp)
            ann = annualized_pct(rate)

            if self.mgr.should_open(spot_sym, rate):
                self.mgr.open(spot_sym, spot, perp, funding_ts=fts)
                self.notifier.notify(f"🟢 <b>CARRY ABRE</b> {spot_sym}\nFunding anualizado: {ann:+.1f}%")
            elif spot_sym in self.mgr.positions:
                paid = self.mgr.accrue_funding(spot_sym, rate, fts)
                if paid:
                    self.notifier.notify(f"💰 <b>CARRY funding</b> {spot_sym}: {paid:+.4f} USDT")
                if self.mgr.should_close(spot_sym, rate):
                    net = self.mgr.close(spot_sym, spot, perp)
                    self.notifier.notify(
                        f"🔴 <b>CARRY CIERRA</b> {spot_sym}\nanualizado {ann:+.1f}% | P&L {net:+.2f}")

        # Vigilancia de liquidación (solo el ejecutor real la implementa).
        monitor = getattr(self.mgr, "monitor", None)
        if callable(monitor):
            try:
                monitor()
            except Exception:
                logger.exception("[CARRY] fallo en la vigilancia de liquidación")

        eq = self.mgr.equity(prices)
        cash = getattr(self.mgr, "balance", None)
        logger.info("[CARRY] equity %.2f | %s | posiciones %d", eq,
                    f"efectivo {cash:.2f}" if cash is not None else "real/dry-run",
                    len(self.mgr.positions))

    def run_forever(self) -> None:
        logger.info("[CARRY] runner iniciado (PAPER) | símbolos %s | umbral %.1f%% anual",
                    self._symbols, self.cfg.min_annualized_pct)
        while True:
            try:
                self.cycle()
            except Exception:
                logger.exception("[CARRY] error en el ciclo; continúo")
            time.sleep(self.cfg.poll_interval_seconds)
