"""Capa de acceso al exchange (KuCoin o Bybit EU) mediante ccxt.

Aísla el resto del bot de los detalles de la API. Para market data no hacen
falta credenciales; sólo se usan al enviar órdenes reales (modo live).
"""

from __future__ import annotations

import functools
import logging
import random
import time

import pandas as pd

from .config import Config

logger = logging.getLogger(__name__)

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

# Un "último precio" a más de esto de la horquilla del propio ticker no es de fiar.
PRICE_BAND_TOLERANCE = 0.01
SUSPECT_LOG_SECONDS = 300.0      # como mucho un aviso por símbolo en este tiempo


def ticker_price(ticker: dict, tolerance: float = PRICE_BAND_TOLERANCE) -> tuple[float | None, bool]:
    """Precio utilizable de un ticker de ccxt y si su último precio es de fiar: (precio, fiable).

    Si el exchange no manda el último precio, ccxt lo DEDUCE de otros campos (media y
    variación de 24 h) y puede devolver un valor al que nunca se negoció: en KuCoin esa
    "media" es la del día anterior, no la de apertura y cierre que ccxt supone. La
    compra y la venta del libro sí vienen tal cual del exchange, así que sirven de
    contraste: un último precio fuera de esa horquilla (más un margen) se descarta y se
    devuelve el punto medio del libro con fiable=False.
    Sin último precio se usa la mejor compra (o la venta), como hasta ahora."""
    last = ticker.get("last") or ticker.get("close")
    bid, ask = ticker.get("bid"), ticker.get("ask")
    book = bool(bid and ask and 0 < bid <= ask)
    if not last:
        price = bid or ask
        return (float(price) if price else None), True
    last = float(last)
    if book and not (bid * (1 - tolerance) <= last <= ask * (1 + tolerance)):
        return (float(bid) + float(ask)) / 2, False
    return last, True


def is_rate_limited(exc: BaseException) -> bool:
    """¿Es un rechazo por exceso de peticiones? KuCoin responde a veces con el código
    429000 ("Too many requests. System-level rate limit exceeded."), que ccxt no
    reconoce y lanza como ExchangeError genérico en vez de RateLimitExceeded."""
    text = str(exc).lower()
    return "429000" in text or "too many requests" in text


def with_network_retry(
    func=None,
    *,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff: float = 2.0,
    jitter: bool = True,
):
    """Decorador para reintentar operaciones de red transitorias con exponential backoff y jitter.

    Captura errores de red y rate limits (ccxt.NetworkError, ccxt.RateLimitExceeded,
    ConnectionError, etc., y el 429000 de KuCoin, ver `is_rate_limited`) y reintenta con
    backoff. Propaga inmediatamente errores fatales
    (ccxt.AuthenticationError, ccxt.InsufficientFunds, ccxt.InvalidOrder, etc.).
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                import ccxt
                fatal_exceptions = (
                    ccxt.AuthenticationError,
                    ccxt.InsufficientFunds,
                    ccxt.InvalidOrder,
                    ccxt.BadSymbol,
                    ccxt.OrderNotFound,
                )
                retryable_exceptions = (
                    ccxt.NetworkError,
                    ccxt.RateLimitExceeded,
                    ccxt.ExchangeNotAvailable,
                    ccxt.RequestTimeout,
                    ccxt.DDoSProtection,
                    ConnectionError,
                    TimeoutError,
                    OSError,
                )
            except ImportError:
                fatal_exceptions = ()
                retryable_exceptions = (ConnectionError, TimeoutError, OSError)

            delay = initial_delay
            for attempt in range(1, max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except fatal_exceptions:
                    raise
                except Exception as exc:
                    if not isinstance(exc, retryable_exceptions) and not is_rate_limited(exc):
                        raise
                    if attempt == max_retries:
                        logger.error(
                            "Fallo definitivo tras %d intentos en %s: %s",
                            max_retries, fn.__name__, exc,
                        )
                        raise
                    sleep_time = delay * (1 + random.uniform(0, 0.25) if jitter else 1.0)
                    logger.warning(
                        "[REINTENTO %d/%d] Error transitorio en %s (%s). Esperando %.2fs...",
                        attempt, max_retries, fn.__name__, exc, sleep_time,
                    )
                    time.sleep(sleep_time)
                    delay *= backoff
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


class Exchange:
    """Wrapper fino sobre el cliente de ccxt del exchange configurado. Las diferencias
    entre exchanges (parámetros de las órdenes de stop, consulta de órdenes, tamaño de
    página de velas) se resuelven aquí; el resto del bot no las ve."""

    _is_bybit = False
    _ohlcv_page = 1500

    def __init__(self, config: Config):
        self.config = config
        self._is_bybit = config.exchange.startswith("bybit")
        self._ohlcv_page = 1000 if self._is_bybit else 1500     # máximo de velas por petición
        self._client = self._build_client()

    def _warn_suspect(self, symbol: str, ticker: dict, used: str) -> None:
        """Deja constancia de un último precio descartado, sin llenar el log."""
        seen = self.__dict__.setdefault("_suspect_logged", {})
        now = time.monotonic()
        if now - seen.get(symbol, -SUSPECT_LOG_SECONDS) < SUSPECT_LOG_SECONDS:
            return
        seen[symbol] = now
        logger.warning(
            "[%s] Último precio del ticker fuera de su horquilla (último %s, compra %s, venta %s): %s",
            symbol, ticker.get("last"), ticker.get("bid"), ticker.get("ask"), used,
        )

    def _build_client(self):
        import ccxt  # import perezoso: el resto del código no depende de ccxt

        params: dict = {
            "enableRateLimit": True,
            # Ajusta la marca de tiempo a la hora del servidor del exchange para
            # evitar rechazos de firma si el reloj local va desfasado.
            "options": {"adjustForTimeDifference": True},
        }
        if self._is_bybit:
            # ccxt asume derivados por defecto en Bybit; el bot solo opera al contado.
            params["options"]["defaultType"] = "spot"
        creds = self.config.credentials
        if creds.is_complete:
            params.update(apiKey=creds.api_key, secret=creds.api_secret)
            if creds.api_passphrase:
                params["password"] = creds.api_passphrase
        client = getattr(ccxt, self.config.exchange)(params)
        if creds.is_complete:
            # Carga YA la diferencia con el reloj del servidor: sin esto, la
            # opción adjustForTimeDifference no tiene efecto en la primera
            # petición firmada y el exchange la rechaza por la marca de tiempo.
            try:
                client.load_time_difference()
            except Exception:
                logger.warning("No se pudo cargar la diferencia horaria del servidor")
        return client

    def _normalize_symbol(self, symbol: str) -> str:
        if self.config.exchange == "kucoinfutures" and ":" not in symbol:
            return f"{symbol}:USDT"
        return symbol

    @with_network_retry
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

    @with_network_retry
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

    @with_network_retry
    def fetch_ohlcv_history(
        self, symbol: str, timeframe: str, total: int
    ) -> pd.DataFrame:
        """Descarga `total` velas paginando hacia atrás (el exchange limita las velas
        por petición). Devuelve las `total` más recientes, ordenadas por tiempo."""
        symbol = self._normalize_symbol(symbol)
        tf_ms = self._client.parse_timeframe(timeframe) * 1000
        now = self._client.milliseconds()
        since = now - total * tf_ms
        rows: list = []
        while since < now:
            batch = self._client.fetch_ohlcv(symbol, timeframe, since=since, limit=self._ohlcv_page)
            if not batch or len(batch) == 0:
                break
            
            # Evitar bucle infinito
            if len(rows) > 0 and batch[-1][0] <= rows[-1][0]:
                since = rows[-1][0] + tf_ms
                continue

            rows.extend(batch)
            since = batch[-1][0] + tf_ms
            if len(rows) >= total:
                break

        df = pd.DataFrame(rows, columns=OHLCV_COLUMNS).drop_duplicates(subset="timestamp")
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp").sort_index()
        return df.tail(total)

    @with_network_retry
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

    @with_network_retry
    def fetch_last_price(self, symbol: str) -> float:
        """Último precio. Una recién listada puede no tener 'last' aún (sin trades):
        cae a close/bid/ask y, si tampoco hay, lanza ValueError limpio (no TypeError
        por float(None)). Si el último precio no cuadra con el libro del propio ticker
        (ver `ticker_price`), devuelve el punto medio del libro."""
        symbol = self._normalize_symbol(symbol)
        ticker = self._client.fetch_ticker(symbol)
        price, trusted = ticker_price(ticker)
        if price is None:
            raise ValueError(f"{symbol}: sin precio disponible todavía (recién listada)")
        if not trusted:
            self._warn_suspect(symbol, ticker, "uso el punto medio del libro")
        return price

    def fetch_last_prices(self, symbols: list[str]) -> dict[str, float]:
        """Últimos precios de varios símbolos en UNA consulta (sondeo rápido de salidas).
        Sin reintentos: si falla, el llamador se salta ese sondeo. Los símbolos sin
        precio, o con un último precio que no cuadra con el libro del propio ticker
        (ver `ticker_price`), se omiten del resultado: con ese dato se deciden ventas."""
        if not symbols:
            return {}
        wanted = {self._normalize_symbol(s): s for s in symbols}
        tickers = self._client.fetch_tickers(list(wanted))
        prices: dict[str, float] = {}
        for normalized, original in wanted.items():
            ticker = tickers.get(normalized) or {}
            price, trusted = ticker_price(ticker)
            if not trusted:
                self._warn_suspect(original, ticker, "me salto esta moneda en este sondeo")
                continue
            if price:
                prices[original] = price
        return prices

    def fetch_book_price(self, symbol: str, side: str) -> float:
        """Precio al que se ejecutaría YA una orden a mercado: la mejor compra del libro
        si se va a vender (`side='sell'`), la mejor venta si se va a comprar. Viene del
        libro de órdenes, no de un ticker, así que sirve de segunda lectura independiente
        antes de vender. Sin reintentos: quien llama decide qué hacer si falla."""
        book = self._client.fetch_order_book(self._normalize_symbol(symbol), 20)
        levels = book.get("bids" if side == "sell" else "asks") or []
        if not levels:
            raise ValueError(f"{symbol}: libro de órdenes vacío")
        return float(levels[0][0])

    @with_network_retry
    def fetch_balance(self, currency: str) -> float:
        """Saldo libre de una moneda. Requiere credenciales (modo live)."""
        balance = self._client.fetch_balance()
        return float(balance.get("free", {}).get(currency, 0.0))

    @with_network_retry
    def fetch_balances_total(self) -> dict[str, float]:
        """Saldo TOTAL (libre + bloqueado) por moneda. Para reconciliar posiciones
        readoptadas contra lo que de verdad hay en la cuenta."""
        balance = self._client.fetch_balance()
        total = balance.get("total") or {}
        return {k: float(v) for k, v in total.items() if v}

    @with_network_retry
    def fetch_trading_fee(self, symbol: str) -> dict[str, float]:
        """Comisión que la cuenta paga en ese par: {'taker', 'maker'} en tanto por uno.
        Requiere credenciales."""
        fee = self._client.fetch_trading_fee(self._normalize_symbol(symbol))
        return {"taker": float(fee["taker"]), "maker": float(fee["maker"])}

    # --- Metadatos de mercado (límites y precisión) --------------------------------

    @with_network_retry
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

    @with_network_retry
    def amount_to_precision(self, symbol: str, amount: float) -> float:
        symbol = self._normalize_symbol(symbol)
        self._client.load_markets()
        return float(self._client.amount_to_precision(symbol, amount))

    # --- Órdenes reales (solo modo live) -------------------------------------------

    def _fetch_order(self, order_id: str, symbol: str) -> dict:
        """Consulta una orden por su identificador (símbolo ya normalizado)."""
        if not self._is_bybit:
            return self._client.fetch_order(order_id, symbol)
        import ccxt
        # Bybit: la consulta directa solo alcanza las últimas órdenes de la cuenta (ccxt
        # exige reconocerlo); si ya no está ahí, se busca en el historial.
        try:
            return self._client.fetch_order(order_id, symbol, {"acknowledged": True})
        except ccxt.OrderNotFound:
            return self._client.fetch_closed_order(order_id, symbol)

    def _await_fill(self, order: dict, symbol: str, retries: int = 6, delay: float = 0.5) -> dict:
        """El exchange no devuelve la cantidad ejecutada al crear la orden (solo el ID):
        hay que consultar la orden después. Reintenta hasta que aparezca el fill."""
        symbol = self._normalize_symbol(symbol)
        order_id = order.get("id") or (order.get("info") or {}).get("orderId")
        if not order_id:
            return order
        result = order
        for _ in range(retries):
            try:
                result = self._fetch_order(order_id, symbol)
            except Exception:
                logger.warning("No pude consultar la orden %s todavía; reintento", order_id)
            if float(result.get("filled") or 0) > 0:
                return result
            time.sleep(delay)
        return result

    def fetch_order_fill(self, order_id: str, symbol: str) -> dict | None:
        """Consulta UNA vez una orden ya enviada. Devuelve la orden si ya consta su
        ejecución, o None si el exchange todavía no la refleja."""
        result = self._fetch_order(order_id, self._normalize_symbol(symbol))
        return result if float(result.get("filled") or 0) > 0 else None

    def create_market_buy(self, symbol: str, cost: float) -> dict:
        """Compra a mercado gastando `cost` en moneda de cotización.

        KuCoin y Bybit usan el importe en quote para las compras a mercado, no
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

    # --- Órdenes de stop en el exchange (red de seguridad; ver exchange_stops.py) -------

    @staticmethod
    def _stop_order_view(order: dict) -> dict:
        """Campos que usa el bot de una orden de stop de ccxt."""
        info = order.get("info") or {}
        return {
            "id": order.get("id") or info.get("id") or info.get("orderId"),
            "client_id": order.get("clientOrderId") or info.get("clientOid") or info.get("orderLinkId"),
            "symbol": order.get("symbol"),
            "amount": order.get("amount"),
            "trigger_price": order.get("triggerPrice") or order.get("stopPrice") or info.get("stopPrice"),
            "status": order.get("status"),
        }

    def create_stop_sell(self, symbol: str, amount: float, trigger_price: float, client_id: str) -> dict:
        """Orden de VENTA a mercado que se dispara si el precio cae a `trigger_price`.
        El exchange no bloquea el saldo hasta que se dispara (en Bybit se usa la orden
        condicional, no la de TP/SL, que sí lo bloquearía). Sin reintentos: si la
        respuesta se pierde, reintentar podría duplicar la orden."""
        symbol = self._normalize_symbol(symbol)
        self._client.load_markets()
        amount = float(self._client.amount_to_precision(symbol, amount))
        price = float(self._client.price_to_precision(symbol, trigger_price))
        if amount <= 0 or price <= 0:
            raise ValueError(f"{symbol}: cantidad o precio de stop no válidos ({amount}, {price})")
        if self._is_bybit:
            params = {"triggerPrice": price, "clientOrderId": client_id}
        else:
            params = {"stopLossPrice": price, "clientOid": client_id}
        order = self._client.create_order(symbol, "market", "sell", amount, None, params)
        view = self._stop_order_view(order)
        view.update(amount=amount, trigger_price=price, client_id=client_id, symbol=symbol)
        return view

    def cancel_stop_order(self, order_id: str, symbol: str) -> bool:
        """Cancela una orden de stop aún sin disparar. False si ya no existe
        (disparada, cancelada o desconocida); otros fallos se propagan."""
        import ccxt
        try:
            self._client.cancel_order(order_id, self._normalize_symbol(symbol) if symbol else None, {"trigger": True})
            return True
        except (ccxt.OrderNotFound, ccxt.InvalidOrder):
            return False

    @with_network_retry
    def fetch_open_stop_orders(self) -> list[dict]:
        """Órdenes de stop vivas (sin disparar) de la cuenta."""
        # Bybit devuelve 20 por defecto; 50 es su máximo y sobra para las posiciones del bot.
        orders = self._client.fetch_open_orders(None, None, 50 if self._is_bybit else None, {"trigger": True})
        return [self._stop_order_view(o) for o in orders]

    @with_network_retry
    def contract_size(self, symbol: str) -> float:
        symbol = self._normalize_symbol(symbol)
        self._client.load_markets()
        return float(self._client.market(symbol).get("contractSize") or 1.0)

    @with_network_retry
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


__all__ = [
    "Exchange",
    "OHLCV_COLUMNS",
    "ticker_price",
    "with_network_retry",
]
