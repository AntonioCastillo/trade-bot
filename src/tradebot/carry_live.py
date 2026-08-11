"""Ejecutor REAL del carry delta-neutral: pata spot (largo) + pata perp (corto).

Misma interfaz que `CarryManager` (paper) para que `CarryRunner` lo use igual:
should_open / should_close / open / accrue_funding / close / equity / positions,
más `monitor()` para vigilar la liquidación de la pata corta.

SEGURIDAD:
  - Ambas patas comparten el flag `dry_run` del broker: en dry-run NO se envía
    NADA (ni spot ni perp), solo se registra lo que se haría.
  - Notional por posición topado por `carry.max_notional_usdt` (tope duro).
  - Apalancamiento 1x aislado (la liquidación queda lejísimos).
  - Si al abrir el corto falla tras comprar el spot, se DESHACE el spot para no
    quedar direccionalmente expuesto.
  - `monitor()` cierra de emergencia si el precio se acerca a la liquidación.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .carry import annualized_pct
from .config import Config
from .exchange import Exchange
from .execution.futures import FuturesBroker
from .notifier import Notifier, NullNotifier

logger = logging.getLogger(__name__)


@dataclass
class LiveCarryPosition:
    symbol: str            # spot, p.ej. ETH/USDT
    perp_symbol: str       # perp, p.ej. ETH/USDT:USDT
    notional: float        # USDT objetivo por pata
    spot_entry: float
    spot_amount: float     # base comprada en spot (fill real)
    perp_entry: float
    perp_contracts: float  # contratos vendidos en el perp (fill real)
    funding_collected: float = 0.0   # informativo (en real lo abona el exchange)
    last_funding_ts: int = 0
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _fill(result: dict, fallback_price: float, fallback_amount: float) -> tuple[float, float, float]:
    """(precio, cantidad, fee) a partir de un dict de orden ccxt (o simulado)."""
    price = float(result.get("average") or result.get("price") or fallback_price)
    amount = float(result.get("filled") or fallback_amount)
    fee = float((result.get("fee") or {}).get("cost") or 0.0)
    return price, amount, fee


class LiveCarryExecutor:
    def __init__(self, config: Config, spot: Exchange, broker: FuturesBroker,
                 notifier: Notifier | None = None):
        self.config = config
        self.cfg = config.carry
        self.spot = spot
        self.broker = broker
        self.notifier = notifier or NullNotifier()
        self.dry_run = broker.dry_run
        self.positions: dict[str, LiveCarryPosition] = {}

    # --- Decisiones (idénticas al paper) ------------------------------------------

    def should_open(self, symbol: str, rate: float) -> bool:
        return (symbol not in self.positions
                and annualized_pct(rate) >= self.cfg.min_annualized_pct)

    def should_close(self, symbol: str, rate: float) -> bool:
        return (symbol in self.positions
                and annualized_pct(rate) < self.cfg.exit_annualized_pct)

    # --- Sizing -------------------------------------------------------------------

    def _target_notional(self) -> float:
        """USDT por posición: % del USDT spot libre, topado por max_notional_usdt,
        y limitado por el margen disponible en futuros (con 1x, margen≈notional)."""
        if self.dry_run:
            # Sin balances reales: simulamos holgura para que mande el tope duro.
            spot_free = fut_free = self.cfg.max_notional_usdt / max(self.cfg.notional_pct, 1e-9)
        else:
            spot_free = self.spot.fetch_balance("USDT")
            fut_free = self.broker.fetch_free_usdt()
        by_pct = spot_free * self.cfg.notional_pct
        margin_room = fut_free * self.broker.leverage
        return max(0.0, min(self.cfg.max_notional_usdt, by_pct, margin_room))

    # --- Operativa ----------------------------------------------------------------

    def open(self, symbol: str, spot_price: float, perp_price: float,
             funding_ts: int = 0) -> LiveCarryPosition | None:
        perp_symbol = symbol + ":USDT"
        notional = self._target_notional()
        if notional < 1.0:  # KuCoin: por debajo del mínimo no tiene sentido
            logger.warning("[CARRY-LIVE] notional %.2f insuficiente para %s; no abro",
                           notional, symbol)
            self.notifier.notify(f"⚠️ <b>CARRY</b> sin margen suficiente para {symbol}")
            return None

        contracts = self.broker.contracts_for_notional(perp_symbol, notional, perp_price)
        if contracts <= 0:
            logger.warning("[CARRY-LIVE] %s: notional %.2f no llega a 1 contrato; no abro",
                           perp_symbol, notional)
            return None

        # 1) Pata spot (largo).
        if self.dry_run:
            logger.warning("[CARRY-LIVE][DRY-RUN] COMPRA SPOT %s por %.2f USDT — NO enviado",
                           symbol, notional)
            spot_p, spot_amt = spot_price, notional / spot_price
        else:
            res = self.spot.create_market_buy(symbol, notional)
            spot_p, spot_amt, _ = _fill(res, spot_price, notional / spot_price)

        # 2) Pata perp (corto). Si falla, deshacer el spot para no quedar largo neto.
        try:
            res = self.broker.open_short(perp_symbol, contracts, perp_price)
            perp_p, perp_c, _ = _fill(res, perp_price, contracts)
        except Exception as exc:
            logger.exception("[CARRY-LIVE] fallo al abrir el corto de %s; deshago el spot", symbol)
            if not self.dry_run:
                try:
                    self.spot.create_market_sell(symbol, spot_amt)
                except Exception:
                    logger.exception("[CARRY-LIVE] ¡NO pude deshacer el spot de %s! Revisar a mano", symbol)
                    self.notifier.notify(
                        f"🛑 <b>CARRY</b> {symbol}: corto falló Y no pude deshacer el spot. "
                        f"REVISA MANUALMENTE (quedas largo {spot_amt:.6f}).")
            self.notifier.notify(f"⚠️ <b>CARRY</b> no pude abrir el corto de {symbol}: "
                                 f"{type(exc).__name__}. Spot deshecho.")
            return None

        pos = LiveCarryPosition(
            symbol=symbol, perp_symbol=perp_symbol, notional=notional,
            spot_entry=spot_p, spot_amount=spot_amt,
            perp_entry=perp_p, perp_contracts=perp_c, last_funding_ts=funding_ts,
        )
        self.positions[symbol] = pos
        tag = "DRY-RUN" if self.dry_run else "REAL"
        logger.info("[CARRY-LIVE][%s] ABRE %s | spot %.6f x%.6f | corto %s x%s @ %.6f",
                    tag, symbol, spot_p, spot_amt, perp_symbol, perp_c, perp_p)
        return pos

    def accrue_funding(self, symbol: str, rate: float, funding_ts: int) -> float:
        """En real el funding lo abona el exchange al monedero de futuros; aquí solo
        se registra el importe esperado (informativo) para la notificación."""
        pos = self.positions.get(symbol)
        if pos is None or funding_ts <= pos.last_funding_ts:
            return 0.0
        expected = rate * pos.notional
        pos.funding_collected += expected
        pos.last_funding_ts = funding_ts
        return expected

    def close(self, symbol: str, spot_price: float, perp_price: float) -> float:
        pos = self.positions.pop(symbol)
        if self.dry_run:
            logger.warning("[CARRY-LIVE][DRY-RUN] VENDE SPOT %s x%.6f y CIERRA corto %s x%s — NO enviado",
                           symbol, pos.spot_amount, pos.perp_symbol, pos.perp_contracts)
            spot_out = pos.spot_amount * spot_price
        else:
            res = self.spot.create_market_sell(symbol, pos.spot_amount)
            sp, sa, _ = _fill(res, spot_price, pos.spot_amount)
            spot_out = sa * sp
            try:
                self.broker.close_short(pos.perp_symbol, pos.perp_contracts, perp_price)
            except Exception:
                logger.exception("[CARRY-LIVE] ¡fallo al cerrar el corto de %s! Revisar a mano", symbol)
                self.notifier.notify(f"🛑 <b>CARRY</b> {symbol}: vendí el spot pero el corto NO cerró. "
                                     f"REVISA MANUALMENTE.")
        perp_pnl = (pos.perp_entry - perp_price) * pos.perp_contracts * self.broker.contract_size(pos.perp_symbol)
        net = (spot_out - pos.notional) + perp_pnl + pos.funding_collected
        logger.info("[CARRY-LIVE] CIERRA %s | funding≈%.4f | P&L neto≈%.4f", symbol, pos.funding_collected, net)
        return net

    # --- Estado / vigilancia ------------------------------------------------------

    def equity(self, prices: dict[str, tuple[float, float]]) -> float:
        """MTM aproximado: USDT spot libre + valor spot de las posiciones +
        equity del monedero de futuros. En dry-run no hay balances reales."""
        if self.dry_run:
            total = 0.0
            for sym, pos in self.positions.items():
                spot_now, perp_now = prices.get(sym, (pos.spot_entry, pos.perp_entry))
                perp_pnl = (pos.perp_entry - perp_now) * pos.perp_contracts * self.broker.contract_size(pos.perp_symbol)
                total += pos.spot_amount * spot_now + perp_pnl
            return total
        total = self.spot.fetch_balance("USDT") + self.broker.fetch_free_usdt()
        for sym, pos in self.positions.items():
            spot_now, _ = prices.get(sym, (pos.spot_entry, pos.perp_entry))
            total += pos.spot_amount * spot_now
        return total

    def monitor(self) -> None:
        """Vigila cada corto: si el precio se acerca a la liquidación, cierra de
        emergencia (protege el capital ante un short squeeze)."""
        if self.dry_run:
            return
        buffer = self.cfg.liquidation_buffer_pct
        for symbol, pos in list(self.positions.items()):
            p = self.broker.fetch_position(pos.perp_symbol)
            if not p or p["liquidation_price"] <= 0 or p["mark_price"] <= 0:
                continue
            # Corto: liquida al SUBIR. Distancia relativa a la liquidación.
            dist = (p["liquidation_price"] - p["mark_price"]) / p["mark_price"]
            if dist <= buffer:
                logger.warning("[CARRY-LIVE] %s a %.1f%% de la liquidación (<%.0f%%): CIERRE DE EMERGENCIA",
                               symbol, dist * 100, buffer * 100)
                self.notifier.notify(f"🛑 <b>CARRY</b> {symbol} cerca de liquidación "
                                     f"({dist*100:.1f}%): cierre de emergencia.")
                spot_now = self.spot.fetch_last_price(symbol)
                self.close(symbol, spot_now, p["mark_price"])
