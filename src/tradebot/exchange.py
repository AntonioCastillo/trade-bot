"""Capa de acceso al exchange (KuCoin) mediante ccxt.

Aísla el resto del bot de los detalles de la API. Para market data no hacen
falta credenciales; sólo se usan al enviar órdenes reales (modo live).
"""

from __future__ import annotations

import logging
import time

import pandas as pd

from .config import Config

logger = logging.getLogger(__name__)

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


class Exchange:
    """Wrapper fino sobre ccxt.kucoin."""

    def __init__(self, config: Config):
        self.config = config
        self._client = self._build_client()

    def _build_client(self):
        import ccxt  # import perezoso: el resto del código no depende de ccxt

        params: dict = {
            "enableRateLimit": True,
            # Ajusta la marca de tiempo a la hora del servidor de KuCoin para
            # evitar "Invalid KC-API-TIMESTAMP" si el reloj local va desfasado.
            "options": {"adjustForTimeDifference": True},
        }
        creds = self.config.credentials
        if creds.is_complete:
            params.update(
                apiKey=creds.api_key,
                secret=creds.api_secret,
                password=creds.api_passphrase,
            )
        if self.config.exchange == "kucoinfutures":
            client = ccxt.kucoinfutures(params)
        else:
            client = ccxt.kucoin(params)
        if creds.is_complete:
            # Carga YA la diferencia con el reloj del servidor: sin esto, la
            # opción adjustForTimeDifference no tiene efecto en la primera
            # petición firmada y KuCoin devuelve "Invalid KC-API-TIMESTAMP".
            try:
                client.load_time_difference()
            except Exception:
                logger.warning("No se pudo cargar la diferencia horaria del servidor")
        return client

    def _normalize_symbol(self, symbol: str) -> str:
        if self.config.exchange == "kucoinfutures" and ":" not in symbol:
            return f"{symbol}:USDT"
        return symbol

    def market_symbols(self) -> set[str]:
        """Conjunto de símbolos que el exchange ofrece realmente."""
        self._client.load_markets()
        symbols = set(self._client.markets.keys())
        if self.config.exchange == "kucoinfutures":
            normalized = set()
            for s in symbols:
                normalized.add(s)
                if ":" in s:
                    normalized.add(s.split(":")[0])
            return normalized
        return symbols

    def fetch_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> pd.DataFrame:
        """Devuelve un DataFrame de velas indexado por tiempo (UTC)."""
        symbol = self._normalize_symbol(symbol)
        raw = self._client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=OHLCV_COLUMNS)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp")
        return df

    def fetch_ohlcv_history(
        self, symbol: str, timeframe: str, total: int
    ) -> pd.DataFrame:
        """Descarga `total` velas paginando hacia atrás (KuCoin limita a ~1500
        por petición). Devuelve las `total` más recientes, ordenadas por tiempo."""
        symbol = self._normalize_symbol(symbol)
        tf_ms = self._client.parse_timeframe(timeframe) * 1000
        now = self._client.milliseconds()
        since = now - total * tf_ms
        rows: list = []
        while since < now:
            batch = self._client.fetch_ohlcv(symbol, timeframe, since=since, limit=1500)
            if not batch:
                break
            rows.extend(batch)
            since = batch[-1][0] + tf_ms
            if len(batch) < 1500:
                break

        df = pd.DataFrame(rows, columns=OHLCV_COLUMNS).drop_duplicates(subset="timestamp")
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp").sort_index()
        return df.tail(total)

    def fetch_funding_history(self, symbol: str, total: int = 1095) -> list[dict]:
        """Histórico de funding rates del perpetuo (KuCoin futures), paginado.
        `symbol` en formato unificado ccxt, p.ej. 'BTC/USDT:USDT'. Público."""
        import ccxt
        symbol = self._normalize_symbol(symbol)

        cl = ccxt.kucoinfutures({"enableRateLimit": True})
        period_ms = 8 * 3600 * 1000   # funding cada 8h
        now = cl.milliseconds()
        since = now - total * period_ms
        rows: list = []
        while since < now:
            batch = cl.fetch_funding_rate_history(symbol, since=since, limit=200)
            if not batch:
                break
            rows.extend(batch)
            since = batch[-1]["timestamp"] + period_ms
            if len(batch) < 200:
                break
        seen: set = set()
        out: list = []
        for r in sorted(rows, key=lambda r: r["timestamp"]):
            t = r["timestamp"]
            if t not in seen and r.get("fundingRate") is not None:
                seen.add(t)
                out.append(r)
        return out[-total:]

    def fetch_last_price(self, symbol: str) -> float:
        """Último precio. Una recién listada puede no tener 'last' aún (sin trades):
        cae a close/bid/ask y, si tampoco hay, lanza ValueError limpio (no TypeError
        por float(None))."""
        symbol = self._normalize_symbol(symbol)
        ticker = self._client.fetch_ticker(symbol)
        price = (ticker.get("last") or ticker.get("close")
                 or ticker.get("bid") or ticker.get("ask"))
        if price is None:
            raise ValueError(f"{symbol}: sin precio disponible todavía (recién listada)")
        return float(price)

    def fetch_balance(self, currency: str) -> float:
        """Saldo libre de una moneda. Requiere credenciales (modo live)."""
        balance = self._client.fetch_balance()
        return float(balance.get("free", {}).get(currency, 0.0))

    def fetch_balances_total(self) -> dict[str, float]:
        """Saldo TOTAL (libre + bloqueado) por moneda. Para reconciliar posiciones
        readoptadas contra lo que de verdad hay en la cuenta."""
        balance = self._client.fetch_balance()
        total = balance.get("total") or {}
        return {k: float(v) for k, v in total.items() if v}

    # --- Metadatos de mercado (límites y precisión) --------------------------------

    def market_limits(self, symbol: str) -> dict:
        """Devuelve mínimos de coste (quote) y cantidad (base) del par."""
        symbol = self._normalize_symbol(symbol)
        self._client.load_markets()
        m = self._client.market(symbol)
        limits = m.get("limits") or {}
        return {
            "min_cost": (limits.get("cost") or {}).get("min"),
            "min_amount": (limits.get("amount") or {}).get("min"),
        }

    def amount_to_precision(self, symbol: str, amount: float) -> float:
        symbol = self._normalize_symbol(symbol)
        self._client.load_markets()
        return float(self._client.amount_to_precision(symbol, amount))

    # --- Órdenes reales (solo modo live) -------------------------------------------

    def _await_fill(self, order: dict, symbol: str, retries: int = 6, delay: float = 0.5) -> dict:
        """KuCoin no devuelve la cantidad ejecutada al crear la orden (solo el ID):
        hay que consultar la orden después. Reintenta hasta que aparezca el fill."""
        symbol = self._normalize_symbol(symbol)
        order_id = order.get("id") or (order.get("info") or {}).get("orderId")
        if not order_id:
            return order
        result = order
        for _ in range(retries):
            try:
                result = self._client.fetch_order(order_id, symbol)
            except Exception:
                logger.warning("No pude consultar la orden %s todavía; reintento", order_id)
            if float(result.get("filled") or 0) > 0:
                return result
            time.sleep(delay)
        return result

    def create_market_buy(self, symbol: str, cost: float) -> dict:
        """Compra a mercado gastando `cost` en moneda de cotización (USDT).

        KuCoin usa el importe en quote para las compras a mercado (`funds`), no
        la cantidad de moneda base. ccxt lo maneja con la variante 'with_cost'."""
        symbol = self._normalize_symbol(symbol)
        self._client.load_markets()
        cost = float(self._client.cost_to_precision(symbol, cost))
        logger.warning("Enviando COMPRA REAL: %s por %s (quote)", symbol, cost)
        if self._client.has.get("createMarketBuyOrderWithCost"):
            order = self._client.create_market_buy_order_with_cost(symbol, cost)
        else:
            order = self._client.create_order(
                symbol, "market", "buy", cost, None,
                {"createMarketBuyOrderRequiresPrice": False},
            )
        return self._await_fill(order, symbol)

    def create_market_sell(self, symbol: str, amount: float) -> dict:
        """Vende a mercado `amount` en moneda base, ajustado a la precisión."""
        symbol = self._normalize_symbol(symbol)
        self._client.load_markets()
        amount = float(self._client.amount_to_precision(symbol, amount))
        logger.warning("Enviando VENTA REAL: %s x %s", symbol, amount)
        order = self._client.create_order(symbol, "market", "sell", amount)
        return self._await_fill(order, symbol)

    def contract_size(self, symbol: str) -> float:
        symbol = self._normalize_symbol(symbol)
        self._client.load_markets()
        return float(self._client.market(symbol).get("contractSize") or 1.0)

    def contracts_for_notional(self, symbol: str, notional: float, price: float) -> float:
        symbol = self._normalize_symbol(symbol)
        if price <= 0:
            return 0.0
        raw = notional / (price * self.contract_size(symbol))
        self._client.load_markets()
        try:
            contracts = float(self._client.amount_to_precision(symbol, raw))
        except Exception:
            contracts = float(int(raw))
        return contracts

    def create_futures_order(self, symbol: str, side: str, contracts: float, leverage: float = 1.0) -> dict:
        symbol = self._normalize_symbol(symbol)
        self._client.load_markets()
        contracts = float(self._client.amount_to_precision(symbol, contracts))
        logger.warning("Enviando ORDEN DE FUTUROS REAL (%s): %s x %s contratos (lev %sx)",
                       side.upper(), symbol, contracts, leverage)
        try:
            self._client.set_leverage(leverage, symbol, {"marginMode": "isolated"})
        except Exception:
            logger.warning("No se pudo fijar apalancamiento %sx aislado en %s", leverage, symbol)
        order = self._client.create_order(
            symbol, "market", side, contracts, None,
            {"leverage": leverage, "marginMode": "isolated"}
        )
        return self._await_fill(order, symbol)
