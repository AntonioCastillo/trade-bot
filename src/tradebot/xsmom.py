"""Momentum transversal (cross-sectional) — cabeza de CARTERA.

Rankea una cesta de majors por momentum (retorno de los últimos `lookback_days`),
mantiene el top-K equal-weight (solo-largos), rebalancea cada `rebalance_days`, y
se va a CASH cuando el líder (BTC) está por debajo de su SMA (overlay de tendencia
que doma el drawdown). Validado walk-forward: bate al equal-weight OOS.

Contabilidad PAPER (como el carry al principio): balance simulado, sin órdenes
reales todavía. Corre en un hilo del daemon. NO es consejo.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import Config, XSMomConfig
from .exchange import Exchange
from .notifier import Notifier, NullNotifier

logger = logging.getLogger(__name__)

STATUS_PATH = "data/xsmom_status.json"

# 2ª confirmación para EJECUTAR el rebalanceo con dinero real (aparte de mode=live).
XSMOM_LIVE_CONFIRM_ENV = "TRADEBOT_XSMOM_LIVE_CONFIRM"
XSMOM_LIVE_CONFIRM = "SI XSMOM REAL"


# --- Lógica pura (testable sin red) -------------------------------------------

def rank_momentum(closes: dict[str, pd.Series], lookback: int) -> list[tuple[str, float]]:
    """(símbolo, momentum) ordenados de mayor a menor. Momentum = retorno de las
    últimas `lookback` velas. Descarta los que no tengan histórico suficiente."""
    out: list[tuple[str, float]] = []
    for sym, c in closes.items():
        if c is None or len(c) <= lookback:
            continue
        mom = float(c.iloc[-1] / c.iloc[-1 - lookback] - 1)
        if mom == mom:   # no NaN
            out.append((sym, mom))
    out.sort(key=lambda x: -x[1])
    return out


def trend_bull(closes: dict[str, pd.Series], symbol: str, sma: int) -> bool:
    """True si `symbol` cotiza por encima de su SMA de `sma` velas (régimen alcista)."""
    c = closes.get(symbol)
    if c is None or len(c) < sma:
        return True   # sin datos suficientes -> no bloquear
    return float(c.iloc[-1]) > float(c.rolling(sma).mean().iloc[-1])


def select_targets(closes: dict[str, pd.Series], cfg: XSMomConfig) -> list[str]:
    """Cesta objetivo: top-K por momentum, o [] (cash) si el filtro de tendencia
    dice bear."""
    if cfg.trend_filter and not trend_bull(closes, cfg.trend_symbol, cfg.trend_sma):
        return []
    return [s for s, _ in rank_momentum(closes, cfg.lookback_days)[:cfg.top_k]]


# --- Cartera PAPER ------------------------------------------------------------

class XSMomPortfolio:
    """Cartera equal-weight simulada. `rebalance` mueve a la cesta objetivo cobrando
    comisión solo sobre la parte que rota."""

    def __init__(self, starting_balance: float, fee_pct: float):
        self.cash = float(starting_balance)
        self.holdings: dict[str, float] = {}    # símbolo -> cantidad (base)
        self.fee_pct = fee_pct

    def equity(self, prices: dict[str, float]) -> float:
        total = self.cash
        for s, amt in self.holdings.items():
            total += amt * prices.get(s, 0.0)
        return total

    def holdings_value(self, prices: dict[str, float]) -> dict[str, float]:
        return {s: round(a * prices.get(s, 0.0), 2) for s, a in self.holdings.items()}

    def rebalance(self, targets: list[str], prices: dict[str, float]) -> float:
        """Rebalancea a `targets` equal-weight. Devuelve la comisión pagada."""
        equity = self.equity(prices)
        old_val = {s: a * prices.get(s, 0.0) for s, a in self.holdings.items()}
        per = equity / len(targets) if targets else 0.0
        new_val = {s: per for s in targets}
        turnover = sum(abs(new_val.get(s, 0.0) - old_val.get(s, 0.0))
                       for s in set(old_val) | set(new_val))
        fee = turnover * self.fee_pct
        equity_after = equity - fee
        if targets:
            per_after = equity_after / len(targets)
            self.holdings = {s: per_after / prices[s] for s in targets if prices.get(s)}
            self.cash = 0.0
        else:
            self.holdings = {}
            self.cash = equity_after
        return fee


# --- Ejecutor REAL (rebalanceo de spot) ---------------------------------------

class LiveXSMomExecutor:
    """Rebalanceo REAL de spot. Como xsmom es la ÚNICA estrategia en la cuenta, LEE
    el saldo real como su cartera (robusto ante reinicios). Vende lo que sale del
    top-K, compra lo que entra, para dejar equal-weight. Con `dry_run` solo registra
    las órdenes (estreno seguro de un camino no probado)."""

    MIN_TRADE_USDT = 1.0   # ignora deltas menores (evita churn por dust)

    def __init__(self, config: Config, exchange: Exchange, universe: list[str], dry_run: bool = True):
        self.config = config
        self.exchange = exchange
        self.universe = universe
        self.dry_run = dry_run
        self.quote = config.risk.quote_currency
        self.fee_pct = config.xsmom.fee_pct

    def _balances(self) -> dict[str, float]:
        try:
            return self.exchange.fetch_balances_total()
        except Exception:
            logger.exception("[XSMOM] no pude leer balances reales")
            return {}

    def equity(self, prices: dict[str, float]) -> float:
        bal = self._balances()
        eq = bal.get(self.quote, 0.0)
        for sym in self.universe:
            eq += bal.get(sym.split("/")[0], 0.0) * prices.get(sym, 0.0)
        return eq

    def holdings_value(self, prices: dict[str, float]) -> dict[str, float]:
        bal = self._balances()
        out = {}
        for sym in self.universe:
            v = bal.get(sym.split("/")[0], 0.0) * prices.get(sym, 0.0)
            if v > 0.01:
                out[sym] = round(v, 2)
        return out

    def rebalance(self, targets: list[str], prices: dict[str, float]) -> float:
        bal = self._balances()
        equity = bal.get(self.quote, 0.0) + sum(
            bal.get(s.split("/")[0], 0.0) * prices.get(s, 0.0) for s in self.universe)
        per = equity / len(targets) if targets else 0.0
        tag = "DRY-RUN" if self.dry_run else "REAL"
        traded = 0.0

        # 1) VENTAS: todo lo que no está en el objetivo + sobrepeso de los que están.
        for sym in self.universe:
            price = prices.get(sym, 0.0)
            held_val = bal.get(sym.split("/")[0], 0.0) * price
            tgt_val = per if sym in targets else 0.0
            if held_val - tgt_val > self.MIN_TRADE_USDT and price > 0:
                amount = (held_val - tgt_val) / price
                traded += held_val - tgt_val
                logger.info("[XSMOM][%s] VENDE %s ~%.2f %s", tag, sym, held_val - tgt_val, self.quote)
                if not self.dry_run:
                    try:
                        self.exchange.create_market_sell(sym, self.exchange.amount_to_precision(sym, amount))
                    except Exception as e:
                        logger.warning("[XSMOM] venta %s rechazada: %s", sym, e)

        # 2) COMPRAS: infrapeso de los objetivos, topado por el USDT libre real.
        free = self.MIN_TRADE_USDT * 1e9 if self.dry_run else self.exchange.fetch_balance(self.quote)
        buys = []
        for sym in targets:
            held_val = bal.get(sym.split("/")[0], 0.0) * prices.get(sym, 0.0)
            need = per - held_val
            if need > self.MIN_TRADE_USDT:
                buys.append([sym, need])
        total_need = sum(b[1] for b in buys)
        scale = min(1.0, free / total_need) if total_need > 0 else 1.0   # no gastar más del USDT real
        for sym, need in buys:
            cost = need * scale
            if cost < self.MIN_TRADE_USDT:
                continue
            traded += cost
            logger.info("[XSMOM][%s] COMPRA %s ~%.2f %s", tag, sym, cost, self.quote)
            if not self.dry_run:
                try:
                    self.exchange.create_market_buy(sym, cost)
                except Exception as e:
                    logger.warning("[XSMOM] compra %s rechazada: %s", sym, e)
        return traded * self.fee_pct   # comisión estimada (consistente con el paper)


class LiveXSMomFuturesExecutor:
    """Rebalanceo REAL de FUTUROS para XSMom.
    Sincroniza las posiciones de futuros para mantener únicamente largos en los targets.
    """

    MIN_TRADE_USDT = 5.0   # ignora deltas menores en futuros

    def __init__(self, config: Config, exchange: Exchange, universe: list[str], dry_run: bool = True):
        self.config = config
        self.exchange = exchange
        self.universe = universe
        self.dry_run = dry_run
        self.quote = config.risk.quote_currency
        self.fee_pct = config.xsmom.fee_pct
        self.leverage = getattr(config.xsmom, "leverage", 1.0)

    def _positions(self) -> dict[str, float]:
        try:
            raw = self.exchange._client.fetch_positions()
            positions = {}
            for pos in raw:
                size = float(pos.get("contracts", 0.0) or 0.0)
                if size > 0:
                    symbol = pos.get("symbol")
                    symbol_local = symbol.split(":")[0]
                    side = pos.get("side", "long")
                    if side == "short":
                        size = -size
                    positions[symbol_local] = size
            return positions
        except Exception:
            logger.exception("[XSMOM-FUTURES] no pude leer posiciones reales de futuros")
            return {}

    def equity(self, prices: dict[str, float]) -> float:
        try:
            balance = self.exchange._client.fetch_balance()
            return float(balance.get("total", {}).get(self.quote, 0.0))
        except Exception:
            logger.exception("[XSMOM-FUTURES] no pude leer balance de futuros para equity")
            return 0.0

    def holdings_value(self, prices: dict[str, float]) -> dict[str, float]:
        positions = self._positions()
        out = {}
        for sym, size in positions.items():
            price = prices.get(sym)
            if price and abs(size) > 0:
                out[sym] = round(size * price, 2)
        return out

    def rebalance(self, targets: list[str], prices: dict[str, float]) -> float:
        # 0) GUARDA DE LIQUIDACIÓN (Cierre de emergencia):
        if not self.dry_run:
            buffer = getattr(self.config.xsmom, "liquidation_buffer_pct", 0.15)
            for sym in self.universe:
                try:
                    symbol_ccxt = self.exchange._normalize_symbol(sym)
                    p = self.exchange._client.fetch_position(symbol_ccxt)
                    if p and float(p.get("contracts", 0.0) or 0.0) > 0:
                        liq_price = float(p.get("liquidationPrice") or 0.0)
                        mark_price = float(p.get("markPrice") or 0.0)
                        if liq_price > 0 and mark_price > 0:
                            # Posición LARGA: liquida al BAJAR
                            dist = (mark_price - liq_price) / mark_price
                            if dist <= buffer:
                                logger.warning("[XSMOM-FUTURES] %s a %.1f%% de liquidación (<%.0f%%): CIERRE DE EMERGENCIA",
                                               sym, dist * 100, buffer * 100)
                                amount_contracts = float(p.get("contracts", 0.0))
                                self.exchange.create_futures_order(sym, "sell", amount_contracts, leverage=self.leverage)
                                if hasattr(self.config, "notifier") and self.config.notifier:
                                    self.config.notifier.notify(f"🛑 <b>XSMOM FUTUROS</b> {sym} cerca de liquidación ({dist*100:.1f}%): cierre de emergencia.")
                except Exception as e:
                    logger.warning("[XSMOM-FUTURES] error al verificar liquidación de %s: %s", sym, e)

        total_equity = self.equity(prices)
        if total_equity <= 0:
            logger.warning("[XSMOM-FUTURES] equity <= 0, aborto rebalanceo")
            return 0.0

        per_target = (total_equity * self.leverage) / len(targets) if targets else 0.0
        
        # Límite de Notional máximo por activo
        max_notional = getattr(self.config.xsmom, "max_notional_usdt", 100.0)
        per_target = min(per_target, max_notional)
        
        tag = "DRY-RUN" if self.dry_run else "REAL"
        traded = 0.0

        current_positions = self._positions()
        
        # 1) VENTAS / CIERRES: Cierra posiciones que ya no están en targets
        for sym in self.universe:
            if sym not in targets and current_positions.get(sym, 0.0) > 0:
                amount_contracts = current_positions[sym]
                traded += amount_contracts * prices[sym]
                logger.info("[XSMOM-FUTURES][%s] CIERRA POSICION %s (~%.2f contratos)", tag, sym, amount_contracts)
                if not self.dry_run:
                    try:
                        self.exchange.create_futures_order(sym, "sell", amount_contracts, leverage=self.leverage)
                    except Exception as e:
                        logger.warning("[XSMOM-FUTURES] fallo al cerrar posición en %s: %s", sym, e)

        # 2) COMPRAS / AJUSTES: Abre/ajusta posiciones de los targets
        for sym in targets:
            price = prices.get(sym, 0.0)
            if price <= 0:
                continue

            current_size = current_positions.get(sym, 0.0)
            target_size = per_target / price
            
            contract_size = self.exchange.contract_size(sym)
            target_contracts = round(target_size / contract_size)
            current_contracts = round(current_size)  # FIX: current_size ya son contratos
            
            diff_contracts = target_contracts - current_contracts
            
            if abs(diff_contracts) * contract_size * price > self.MIN_TRADE_USDT:
                trade_value = diff_contracts * contract_size * price
                traded += abs(trade_value)
                
                if diff_contracts > 0:
                    logger.info("[XSMOM-FUTURES][%s] COMPRA LARGOS en %s: +%.1f contratos (~%.2f %s)", 
                                tag, sym, diff_contracts, diff_contracts * contract_size * price, self.quote)
                    if not self.dry_run:
                        try:
                            self.exchange.create_futures_order(sym, "buy", diff_contracts, leverage=self.leverage)
                        except Exception as e:
                            logger.warning("[XSMOM-FUTURES] fallo al aumentar posición en %s: %s", sym, e)
                elif diff_contracts < 0:
                    logger.info("[XSMOM-FUTURES][%s] REDUCE LARGOS en %s: %.1f contratos (~%.2f %s)", 
                                tag, sym, diff_contracts, abs(diff_contracts) * contract_size * price, self.quote)
                    if not self.dry_run:
                        try:
                            self.exchange.create_futures_order(sym, "sell", abs(diff_contracts), leverage=self.leverage)
                        except Exception as e:
                            logger.warning("[XSMOM-FUTURES] fallo al reducir posición en %s: %s", sym, e)

        return traded * self.fee_pct


# --- Runner (hilo del daemon) -------------------------------------------------

class XSMomRunner:
    def __init__(self, config: Config, exchange: Exchange, notifier: Notifier | None = None):
        self.config = config
        self.cfg = config.xsmom
        self.exchange = exchange
        self.notifier = notifier or NullNotifier()
        self.universe = self.cfg.universe or ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        self.pf = self._build_pf()
        self._last_rebalance: datetime | None = None

    def _build_pf(self):
        """El MODO manda: paper -> cartera simulada; live -> ejecutor REAL de spot/futuros."""
        if self.config.mode != "live":
            return XSMomPortfolio(self.config.risk.starting_balance, self.cfg.fee_pct)
        
        if self.config.exchange == "kucoinfutures":
            logger.warning("[XSMOM] ejecutor REAL de FUTUROS activo.")
            self.notifier.notify(
                f"⚙️ <b>XS-Momentum FUTUROS</b> en 🔴 REAL (cesta {len(self.universe)}, top-{self.cfg.top_k}, leverage {self.cfg.leverage}x)"
            )
            return LiveXSMomFuturesExecutor(self.config, self.exchange, self.universe, dry_run=False)
        else:
            logger.warning("[XSMOM] ejecutor REAL de SPOT activo.")
            self.notifier.notify(
                f"⚙️ <b>XS-Momentum SPOT</b> en 🔴 REAL (cesta {len(self.universe)}, top-{self.cfg.top_k})"
            )
            return LiveXSMomExecutor(self.config, self.exchange, self.universe, dry_run=False)

    def _need_bars(self) -> int:
        return max(self.cfg.lookback_days, self.cfg.trend_sma) + 5

    def _fetch_closes(self) -> dict[str, pd.Series]:
        closes: dict[str, pd.Series] = {}
        for sym in self.universe:
            try:
                closes[sym] = self.exchange.fetch_ohlcv(sym, "1d", self._need_bars())["close"]
            except Exception:
                logger.warning("[XSMOM] no pude leer %s; lo salto este ciclo", sym)
        return closes

    def cycle(self) -> None:
        closes = self._fetch_closes()
        if not closes:
            logger.warning("[XSMOM] sin datos; salto rebalanceo")
            return
        prices = {s: float(c.iloc[-1]) for s, c in closes.items() if len(c)}
        targets = select_targets(closes, self.cfg)
        fee = self.pf.rebalance(targets, prices)
        eq = self.pf.equity(prices)
        self._last_rebalance = datetime.now(timezone.utc)

        state = "CASH (bear)" if not targets else ", ".join(t.split("/")[0] for t in targets)
        logger.info("[XSMOM] rebalanceo -> %s | equity %.2f | comisión %.4f", state, eq, fee)
        self.notifier.notify(
            f"🔁 <b>XS-Momentum rebalanceo</b>\nCartera: {state}\n"
            f"Equity: {eq:.2f} {self.config.risk.quote_currency}")
        self._write_status(eq, targets, prices)

    def _write_status(self, equity: float, targets: list[str], prices: dict[str, float]) -> None:
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "equity": round(equity, 2),
            "state": "cash" if not targets else "invested",
            "holdings": self.pf.holdings_value(prices),
            "targets": targets,
            "mode": self.config.mode,
            "lookback_days": self.cfg.lookback_days, "top_k": self.cfg.top_k,
        }
        p = Path(STATUS_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _due(self) -> bool:
        if self._last_rebalance is None:
            return True
        return (datetime.now(timezone.utc) - self._last_rebalance).days >= self.cfg.rebalance_days

    def run_forever(self) -> None:
        logger.info("[XSMOM] runner iniciado (PAPER) | cesta %d | lookback %dd | top-%d | "
                    "rebalanceo cada %dd", len(self.universe), self.cfg.lookback_days,
                    self.cfg.top_k, self.cfg.rebalance_days)
        while True:
            try:
                if self._due():
                    self.cycle()
            except Exception:
                logger.exception("[XSMOM] error en el ciclo; continúo")
            time.sleep(self.cfg.poll_interval_seconds)
