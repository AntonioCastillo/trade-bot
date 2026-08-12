"""Sniper de recién listadas (EXPERIMENTAL — ALTO RIESGO).

Detecta símbolos nuevos en KuCoin y entra fuerte y rápido buscando el pump
inicial. Punto clave y honesto: esto NO es validable con backtesting (una moneda
recién listada no tiene histórico), es donde más pump & dump / rug pulls hay, y
la liquidez/slippage pueden ser extremos. Es más apostar que invertir. Por eso:
  - Usa un % de capital MUY bajo por tiro (config `sniper.position_size_pct`).
  - Salidas CONFIGURABLES: take-profit siempre; stop-loss y timeout OPCIONALES
    (poner a 0 los desactiva). Modo "billete de lotería": TP alto (p.ej. x10), sin
    SL ni timeout → se aguanta cada moneda esperando el pump; casi todas mueren, se
    apuesta a que una explote. `summary()` da el mark-to-market de los billetes.
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
    stop_loss: float             # 0.0 = sin stop (se aguanta el billete)
    deadline: datetime | None    # None = sin timeout (aguantar hasta el objetivo)
    invested: float = 0.0        # capital metido (para el resumen)


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
        # Recién listadas detectadas pero aún sin precio (sin trades): se reintenta
        # su entrada en ciclos siguientes hasta que aparezca precio o se agoten los
        # intentos. Evita perder para siempre las monedas más nuevas (el objetivo).
        self.pending: dict[str, int] = {}
        self._paper_balance = config.risk.starting_balance

    MAX_ENTRY_RETRIES = 20   # ~20 ciclos (p.ej. 10 min a 30s) antes de rendirse

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

    def enter(self, symbol: str) -> bool:
        """Intenta abrir el billete. Devuelve True si entró o no procede reintentar
        (maxed, sin capital, rechazo real); False si falta precio todavía (recién
        listada sin trades) -> reintentar en ciclos siguientes."""
        if len(self.snipes) >= self.cfg.max_concurrent:
            logger.warning("[SNIPER] máximo de tiros simultáneos; ignoro %s", symbol)
            return True
        try:
            price = self.exchange.fetch_last_price(symbol)
        except Exception:
            logger.info("[SNIPER] %s aún sin precio (recién listada); reintento luego", symbol)
            return False
        if price <= 0:
            return False
        capital = self._balance() * self.cfg.position_size_pct
        if capital <= 0:
            return True   # sin capital: no reintentar en bucle
        amount = capital / price

        if self.live:
            try:
                self.exchange.create_market_buy(symbol, capital)
            except Exception as e:
                logger.warning("[SNIPER] compra real rechazada en %s: %s", symbol, e)
                return True   # rechazo real: no reintentar indefinidamente
        else:
            self._paper_balance -= capital

        # SL y timeout son OPCIONALES: 0 (o negativo) = desactivados. En modo
        # "billete de lotería" no hay stop ni timeout: se aguanta hasta el objetivo.
        stop_loss = price * (1 - self.cfg.stop_loss_pct) if self.cfg.stop_loss_pct > 0 else 0.0
        deadline = (datetime.now(timezone.utc) + timedelta(minutes=self.cfg.timeout_minutes)
                    if self.cfg.timeout_minutes > 0 else None)
        take_profit = price * (1 + self.cfg.take_profit_pct)

        snipe = Snipe(
            symbol=symbol, amount=amount, entry_price=price, take_profit=take_profit,
            stop_loss=stop_loss, deadline=deadline, invested=capital,
        )
        self.snipes.append(snipe)
        mult = 1 + self.cfg.take_profit_pct
        sl_txt = f"{stop_loss:.8f}" if stop_loss > 0 else "sin SL"
        to_txt = "sin timeout" if deadline is None else deadline.strftime("%H:%M")
        logger.info("[SNIPER] ENTRA %s @ %.8f (objetivo x%.0f = %.8f | %s | %s)",
                    symbol, price, mult, take_profit, sl_txt, to_txt)
        self.notifier.notify(
            f"🚀 <b>SNIPE</b> nueva listada {symbol}\n"
            f"Entrada: {price:.8f}  |  {capital:.2f} {self.quote}\n"
            f"Objetivo: x{mult:.0f} ({take_profit:.8f})  |  {sl_txt}  |  {to_txt}"
        )
        return True

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
            elif s.stop_loss > 0 and price <= s.stop_loss:
                reason = "stop-loss"
            elif s.deadline is not None and now >= s.deadline:
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

    # --- Resumen (mark-to-market de los billetes abiertos) ------------------------

    def summary(self) -> dict:
        """Valor actual de los billetes abiertos vs lo invertido. Imprescindible
        para 'ver resultados' de una estrategia que casi nunca cierra (x100)."""
        invested = value = 0.0
        best = None
        for s in self.snipes:
            try:
                price = self.exchange.fetch_last_price(s.symbol)
            except Exception:
                price = s.entry_price
            invested += s.invested
            value += price * s.amount
            mult = price / s.entry_price if s.entry_price else 1.0
            if best is None or mult > best[1]:
                best = (s.symbol, mult)
        return {"open": len(self.snipes), "invested": invested, "value": value,
                "pnl": value - invested, "best": best}

    def _log_summary(self) -> None:
        s = self.summary()
        best = f"{s['best'][0]} x{s['best'][1]:.2f}" if s["best"] else "—"
        pct = (s["pnl"] / s["invested"] * 100) if s["invested"] else 0.0
        logger.info("[SNIPER] billetes abiertos=%d | invertido=%.2f | valor=%.2f "
                    "| P&L=%+.2f (%+.1f%%) | mejor=%s",
                    s["open"], s["invested"], s["value"], s["pnl"], pct, best)

    def write_status_file(self, path: str = "data/sniper_status.json") -> None:
        """Vuelca el mark-to-market de los billetes a JSON (para publicar el status)."""
        s = self.summary()
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "open": s["open"], "invested": round(s["invested"], 2),
            "value": round(s["value"], 2), "pnl": round(s["pnl"], 2),
            "best": ({"symbol": s["best"][0], "mult": round(s["best"][1], 2)}
                     if s["best"] else None),
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # --- Bucle --------------------------------------------------------------------

    def run_forever(self) -> None:
        self.bootstrap()
        interval = self.cfg.poll_interval_seconds
        last_summary = 0.0
        try:
            while True:
                try:
                    for symbol in self.poll():
                        logger.info("[SNIPER] ¡NUEVA LISTADA detectada!: %s", symbol)
                        self.pending.setdefault(symbol, 0)
                    # Intenta entrar en las pendientes; reintenta las que aún no
                    # tienen precio (recién listadas) hasta MAX_ENTRY_RETRIES.
                    for symbol in list(self.pending):
                        if self.enter(symbol):
                            del self.pending[symbol]
                        else:
                            self.pending[symbol] += 1
                            if self.pending[symbol] >= self.MAX_ENTRY_RETRIES:
                                logger.warning("[SNIPER] %s sigue sin precio tras %d intentos; "
                                               "lo dejo", symbol, self.pending[symbol])
                                del self.pending[symbol]
                    self.manage()
                    # Resumen periódico (~cada 30 min) para observar la lotería.
                    if self.snipes and time.time() - last_summary >= 1800:
                        self._log_summary()
                        try:
                            self.write_status_file()   # data/sniper_status.json
                        except Exception:
                            logger.warning("[SNIPER] no pude escribir sniper_status.json")
                        last_summary = time.time()
                except Exception:
                    logger.exception("[SNIPER] error en el ciclo; continúo")
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("[SNIPER] interrumpido por el usuario.")
