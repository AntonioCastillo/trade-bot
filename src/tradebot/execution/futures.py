"""Broker de FUTUROS perpetuos (KuCoin futures) para la pata corta del carry.

ATENCIÓN: envía órdenes con dinero real cuando `dry_run=False`. La pata corta
puede LIQUIDARSE si el precio sube con fuerza, así que este broker:
  - fuerza margen AISLADO y apalancamiento bajo (1x por defecto): la liquidación
    queda a ~100% de distancia, no a unos pocos %,
  - dimensiona en CONTRATOS (lot size / contractSize del mercado), no en base,
  - expone la posición (precio de liquidación, margen) para poder vigilarla,
  - por defecto NO envía nada (`dry_run=True`): registra la orden que mandaría.

El resto del carry (decisiones, contabilidad) vive en carry.py / carry_live.py.
"""

from __future__ import annotations

import logging

from ..config import Config

logger = logging.getLogger(__name__)


class FuturesBroker:
    """Wrapper fino sobre ccxt.kucoinfutures para abrir/cerrar el corto perpetuo.

    Con `dry_run=True` (por defecto) NO manda órdenes: calcula y registra lo que
    haría, devolviendo un fill simulado al precio de referencia. Es el modo con el
    que se estrena la pata de futuros en real: ves las órdenes antes de enviarlas.
    """

    def __init__(self, config: Config, leverage: float = 1.0, dry_run: bool = True):
        self.config = config
        self.leverage = max(1.0, float(leverage))
        self.dry_run = dry_run
        self._client = None

    # --- Cliente ------------------------------------------------------------------

    def _c(self):
        if self._client is None:
            import ccxt
            params = {"enableRateLimit": True, "options": {"adjustForTimeDifference": True}}
            creds = self.config.credentials
            if creds.is_complete:
                params.update(apiKey=creds.api_key, secret=creds.api_secret,
                              password=creds.api_passphrase)
            self._client = ccxt.kucoinfutures(params)
            if creds.is_complete:
                try:
                    self._client.load_time_difference()
                except Exception:
                    logger.warning("[FUT] no pude cargar la diferencia horaria")
        return self._client

    # --- Metadatos / sizing -------------------------------------------------------

    def _market(self, symbol: str) -> dict:
        c = self._c()
        c.load_markets()
        return c.market(symbol)

    def contract_size(self, symbol: str) -> float:
        """Tamaño (en moneda base) de 1 contrato del perpetuo."""
        return float(self._market(symbol).get("contractSize") or 1.0)

    def contracts_for_notional(self, symbol: str, notional: float, price: float) -> float:
        """Nº de contratos (redondeado a la precisión del mercado) para cubrir
        `notional` USDT al precio dado. Devuelve 0 si no llega ni a 1 contrato."""
        if price <= 0:
            return 0.0
        raw = notional / (price * self.contract_size(symbol))
        c = self._c()
        try:
            contracts = float(c.amount_to_precision(symbol, raw))
        except Exception:
            contracts = float(int(raw))
        return contracts

    def notional_of(self, symbol: str, contracts: float, price: float) -> float:
        """USDT reales que representan `contracts` contratos a `price`."""
        return contracts * self.contract_size(symbol) * price

    # --- Órdenes ------------------------------------------------------------------

    def _sim_fill(self, side: str, symbol: str, contracts: float, price: float) -> dict:
        fee = self.notional_of(symbol, contracts, price) * self.config.carry.fee_pct
        logger.warning("[FUT][DRY-RUN] %s %s x%s contratos @ %.6f (fee~%.4f) — NO enviado",
                       side.upper(), symbol, contracts, price, fee)
        return {"average": price, "filled": contracts, "fee": {"cost": fee},
                "id": "dry-run", "info": {"dryRun": True}}

    def _set_isolated_leverage(self, symbol: str) -> None:
        if self.dry_run:
            return
        try:
            self._c().set_leverage(self.leverage, symbol, {"marginMode": "isolated"})
        except Exception:
            logger.warning("[FUT] no pude fijar apalancamiento %sx aislado en %s (sigo; "
                           "se pasa también por parámetro de orden)", self.leverage, symbol)

    def _order_params(self) -> dict:
        return {"leverage": self.leverage, "marginMode": "isolated"}

    def open_short(self, symbol: str, contracts: float, price: float) -> dict:
        """Abre (o amplía) el corto: vende `contracts` contratos a mercado."""
        if contracts <= 0:
            raise ValueError(f"[FUT] contratos<=0 para {symbol}")
        self._set_isolated_leverage(symbol)
        if self.dry_run:
            return self._sim_fill("sell", symbol, contracts, price)
        c = self._c()
        contracts = float(c.amount_to_precision(symbol, contracts))
        logger.warning("[FUT] ABRIENDO CORTO REAL %s x%s (lev %sx aislado)",
                       symbol, contracts, self.leverage)
        return c.create_order(symbol, "market", "sell", contracts, None, self._order_params())

    def close_short(self, symbol: str, contracts: float, price: float) -> dict:
        """Cierra el corto: compra `contracts` contratos a mercado (reduceOnly)."""
        if self.dry_run:
            return self._sim_fill("buy", symbol, contracts, price)
        c = self._c()
        contracts = float(c.amount_to_precision(symbol, contracts))
        logger.warning("[FUT] CERRANDO CORTO REAL %s x%s", symbol, contracts)
        return c.create_order(symbol, "market", "buy", contracts, None,
                              {"reduceOnly": True, **self._order_params()})

    # --- Estado -------------------------------------------------------------------

    def fetch_last_price(self, symbol: str) -> float:
        return float(self._c().fetch_ticker(symbol)["last"])

    def fetch_free_usdt(self) -> float:
        """USDT libre en el monedero de FUTUROS (margen disponible)."""
        try:
            bal = self._c().fetch_balance()
            return float((bal.get("free") or {}).get("USDT", 0.0))
        except Exception:
            logger.warning("[FUT] no pude leer el balance de futuros")
            return 0.0

    def fetch_position(self, symbol: str) -> dict | None:
        """Posición actual normalizada, o None si no hay (o en dry-run)."""
        if self.dry_run:
            return None
        try:
            p = self._c().fetch_position(symbol)
        except Exception:
            logger.warning("[FUT] no pude leer la posición de %s", symbol)
            return None
        if not p or not p.get("contracts"):
            return None
        return {
            "contracts": float(p.get("contracts") or 0.0),
            "side": p.get("side"),
            "entry_price": float(p.get("entryPrice") or 0.0),
            "mark_price": float(p.get("markPrice") or 0.0),
            "liquidation_price": float(p.get("liquidationPrice") or 0.0),
            "unrealized_pnl": float(p.get("unrealizedPnl") or 0.0),
            "collateral": float(p.get("collateral") or 0.0),
        }
