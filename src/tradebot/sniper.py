"""Sniper de recién listadas (EXPERIMENTAL — ALTO RIESGO).

Detecta símbolos nuevos en KuCoin y entra fuerte y rápido buscando el pump
inicial. Punto clave y honesto: esto NO es validable con backtesting (una moneda
recién listada no tiene histórico), es donde más pump & dump / rug pulls hay, y
la liquidez/slippage pueden ser extremos. Es más apostar que invertir. Por eso:
  - Usa un % de capital MUY bajo por tiro (config `sniper.position_size_pct`).
  - Cierra por take-profit, stop-loss O timeout (no se queda enganchado).
  - Está DESACTIVADO por defecto (`sniper.enabled: false`).

Modos:
  - paper: simula con el precio real de ticker (sin dinero).
  - live : compra/vende de verdad (requiere claves).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Config
from .exchange import Exchange
from .notifier import Notifier, NullNotifier

logger = logging.getLogger(__name__)


def detect_new_listings(current: set[str], known: set[str], quote: str = "USDT") -> list[str]:
    """Símbolos presentes ahora que no estaban antes, filtrados a pares */quote."""
    return sorted(s for s in (current - known) if s.endswith("/" + quote))


@dataclass
class Snipe:
    symbol: str
    amount: float
    entry_price: float
    take_profit: float
    stop_loss: float
    deadline: datetime


class Sniper:
    def __init__(
        self,
        config: Config,
        exchange: Exchange,
        notifier: Notifier | None = None,
        live: bool = False,
    ):
        self.config = config
        self.cfg = config.sniper
        self.exchange = exchange
        self.notifier = notifier or NullNotifier()
        self.live = live
        self.quote = config.risk.quote_currency
        self.known: set[str] = set()
        self.snipes: list[Snipe] = []
        self._paper_balance = config.risk.starting_balance

    # --- Estado persistente de símbolos conocidos ---------------------------------

    def bootstrap(self) -> None:
        """Fija la línea base de símbolos ya existentes para no 'snipear' todo el
        mercado en el primer arranque."""
        path = Path(self.cfg.baseline_path)
        if path.exists():
            self.known = set(json.loads(path.read_text(encoding="utf-8")))
        else:
            self.known = self.exchange.market_symbols()
            self._save_baseline()
        logger.info("Sniper listo | %d símbolos en línea base | modo=%s",
                    len(self.known), "LIVE" if self.live else "PAPER")

    def _save_baseline(self) -> None:
        path = Path(self.cfg.baseline_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(self.known)), encoding="utf-8")

    # --- Detección y entrada ------------------------------------------------------

    def poll(self) -> list[str]:
        current = self.exchange.market_symbols()
        new = detect_new_listings(current, self.known, self.quote)
        if new:
            self.known |= set(current)
            self._save_baseline()
        return new

    def _balance(self) -> float:
        if self.live:
            return self.exchange.fetch_balance(self.quote)
        return self._paper_balance

    def enter(self, symbol: str) -> None:
        if len(self.snipes) >= self.cfg.max_concurrent:
            logger.warning("[SNIPER] máximo de tiros simultáneos; ignoro %s", symbol)
            return
        try:
            price = self.exchange.fetch_last_price(symbol)
        except Exception:
            logger.exception("[SNIPER] no pude leer precio de %s; lo salto", symbol)
            return
        capital = self._balance() * self.cfg.position_size_pct
        if capital <= 0 or price <= 0:
            return
        amount = capital / price

        if self.live:
            try:
                self.exchange.create_market_buy(symbol, capital)
            except Exception as e:
                logger.warning("[SNIPER] compra real rechazada en %s: %s", symbol, e)
                return
        else:
            self._paper_balance -= capital

        snipe = Snipe(
            symbol=symbol, amount=amount, entry_price=price,
            take_profit=price * (1 + self.cfg.take_profit_pct),
            stop_loss=price * (1 - self.cfg.stop_loss_pct),
            deadline=datetime.now(timezone.utc) + timedelta(minutes=self.cfg.timeout_minutes),
        )
        self.snipes.append(snipe)
        logger.info("[SNIPER] ENTRA %s @ %.8f (TP %.8f / SL %.8f)",
                    symbol, price, snipe.take_profit, snipe.stop_loss)
        self.notifier.notify(
            f"🚀 <b>SNIPE</b> nueva listada {symbol}\n"
            f"Entrada: {price:.8f}  |  {capital:.2f} {self.quote}\n"
            f"TP: {snipe.take_profit:.8f}  SL: {snipe.stop_loss:.8f}"
        )

    # --- Gestión de salidas -------------------------------------------------------

    def manage(self) -> None:
        still: list[Snipe] = []
        now = datetime.now(timezone.utc)
        for s in self.snipes:
            try:
                price = self.exchange.fetch_last_price(s.symbol)
            except Exception:
                still.append(s)
                continue
            reason = None
            if price >= s.take_profit:
                reason = "take-profit"
            elif price <= s.stop_loss:
                reason = "stop-loss"
            elif now >= s.deadline:
                reason = "timeout"
            if reason:
                self._exit(s, price, reason)
            else:
                still.append(s)
        self.snipes = still

    def _exit(self, s: Snipe, price: float, reason: str) -> None:
        if self.live:
            try:
                self.exchange.create_market_sell(s.symbol, s.amount)
            except Exception as e:
                logger.warning("[SNIPER] venta real rechazada en %s: %s; reintentaré", s.symbol, e)
                self.snipes.append(s)
                return
        else:
            self._paper_balance += price * s.amount

        pnl = (price - s.entry_price) * s.amount
        pnl_pct = (price / s.entry_price - 1) * 100
        logger.info("[SNIPER] SALE %s @ %.8f (%s) | P&L %.2f (%.2f%%)",
                    s.symbol, price, reason, pnl, pnl_pct)
        emoji = "✅" if pnl >= 0 else "❌"
        self.notifier.notify(
            f"{emoji} <b>SNIPE cerrado</b> {s.symbol} ({reason})\n"
            f"P&L: {pnl:+.2f} {self.quote} ({pnl_pct:+.2f}%)"
        )

    # --- Bucle --------------------------------------------------------------------

    def run_forever(self) -> None:
        self.bootstrap()
        interval = self.cfg.poll_interval_seconds
        try:
            while True:
                try:
                    for symbol in self.poll():
                        logger.info("[SNIPER] ¡NUEVA LISTADA detectada!: %s", symbol)
                        self.enter(symbol)
                    self.manage()
                except Exception:
                    logger.exception("[SNIPER] error en el ciclo; continúo")
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("[SNIPER] interrumpido por el usuario.")
