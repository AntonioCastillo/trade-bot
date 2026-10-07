"""Simulador con la MECÁNICA REAL del bot en vivo para las cabezas de símbolos fijos.

El backtester (`tradebot.backtester`) decide y sale solo al cierre de vela. En vivo
el daemon hace otra cosa, y eso cambia el resultado:
  - la señal se evalúa una vez por vela CERRADA y se compra a mercado en ese cierre;
  - las salidas (stop / parcial / objetivo / trailing) se comprueban cada 60 s
    (aquí: sobre velas de 15 min, mirando máximo y mínimo);
  - el tamaño es un % del USDT LIBRE, con tope por símbolo, global y de exposición;
  - filtro macro de BTC (precio >= EMA50 diaria) y de cierre fuerte si la cabeza los usa;
  - reglas de pausa de la cabeza (`strike_pause` y `paused_while_open`) y filtro de
    tendencia de la propia moneda (`asset_trend_ema`).

Por defecto cada cabeza se simula SOLA; con --combined se simulan todas juntas,
compitiendo por el saldo libre y los topes como en real. Lee las cabezas de
config.yaml; las que usan rotación RS se miden con scripts/livesim_trend.py.

Uso:
    python scripts/livesim.py                       # todas las cabezas fijas
    python scripts/livesim.py --head grid_lateral   # una sola
    python scripts/livesim.py --start 2025-01-01 --trades 15
    python scripts/livesim.py --combined            # todas juntas, compitiendo por el saldo
    python scripts/livesim.py --refresh             # vuelve a descargar las velas

Las velas se cachean en data/livesim/ (primera ejecución: varios minutos).
"""

from __future__ import annotations

import argparse
import hashlib
import pickle
import sys
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot import indicators  # noqa: E402
from tradebot.config import Config, Instrument, load_config  # noqa: E402
from tradebot.models import SignalType  # noqa: E402
from tradebot.strategy import build_strategy  # noqa: E402

CACHE_DIR = Path("data/livesim")
EXIT_TF = "15min"            # resolución con la que se evalúan las salidas
STOP_SLIPPAGE = 0.002        # deslizamiento extra al saltar un stop (sondeo cada 60 s)
WARMUP_DAYS = 91
CACHE_FRESH_HOURS = 6        # no se vuelve a pedir al exchange una caché más reciente que esto
AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
BTC = "BTC/USDT"


# --- Datos ---------------------------------------------------------------------------

_client = None
_memory: dict[tuple[str, str], tuple[pd.Timestamp, pd.DataFrame]] = {}


def _download(symbol: str, timeframe: str, since: pd.Timestamp) -> pd.DataFrame:
    global _client
    if _client is None:
        import ccxt

        _client = ccxt.kucoin({"enableRateLimit": True})
    client = _client
    rows: list[list] = []
    cursor = int(since.timestamp() * 1000)
    now = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    while True:
        batch = client.fetch_ohlcv(symbol, timeframe, since=cursor, limit=1500)
        batch = [r for r in batch if not rows or r[0] > rows[-1][0]]
        if not batch:
            if not rows and cursor < now:       # aún no cotizaba: avanza hasta su listado
                cursor += 30 * 86_400_000
                continue
            break
        rows += batch
        cursor = rows[-1][0] + 1
        if len(batch) < 100:
            break
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts")


def candles(symbol: str, timeframe: str, since: pd.Timestamp, refresh: bool = False) -> pd.DataFrame:
    """Velas desde `since`, cacheadas en disco. Si hay caché solo descarga lo nuevo,
    y no vuelve a consultar al exchange si se actualizó hace menos de CACHE_FRESH_HOURS."""
    memo = _memory.get((symbol, timeframe))
    if memo is not None and not refresh and memo[0] <= since + pd.Timedelta("2D"):
        return memo[1][memo[1].index >= since]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{symbol.replace('/', '-')}_{timeframe}.pkl"
    cached, cached_since = None, None
    if path.exists() and not refresh:
        stored = pickle.loads(path.read_bytes())
        cached_since, cached = stored if isinstance(stored, tuple) else (stored.index[0], stored)
        if cached_since > since + pd.Timedelta("2D"):
            cached = None                       # la caché no llega tan atrás: se rehace
    if cached is not None and len(cached):
        since_stored = min(cached_since, since)
        if time.time() - path.stat().st_mtime < CACHE_FRESH_HOURS * 3600:
            _memory[(symbol, timeframe)] = (since_stored, cached)
            return cached[cached.index >= since]
        new = _download(symbol, timeframe, cached.index[-1])
        df = pd.concat([cached.iloc[:-1], new]) if len(new) else cached
    else:
        print(f"  descargando {symbol} {timeframe}…", flush=True)
        df = _download(symbol, timeframe, since)
        since_stored = since
    df = df[~df.index.duplicated(keep="last")]
    path.write_bytes(pickle.dumps((since_stored, df)))
    _memory[(symbol, timeframe)] = (since_stored, df)
    return df[df.index >= since]


def pandas_tf(timeframe: str) -> str:
    """Marco de ccxt ('4h', '1d') a alias de pandas ('4h', '1D')."""
    return timeframe[:-1] + "D" if timeframe.endswith("d") else timeframe


def resample(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Agrega a un marco mayor y descarta la última vela (en formación)."""
    return df.resample(pandas_tf(timeframe)).agg(AGG).dropna().iloc[:-1]


class MacroFilter:
    """Réplica de `regime.is_btc_macro_bullish`: BTC >= EMA50 diaria, con la vela
    diaria en formación incluida en la media."""

    def __init__(self, btc_4h: pd.DataFrame, ema_period: int = 50):
        self._close = btc_4h["close"]
        daily = btc_4h.resample("1D").agg(AGG).dropna()
        self._ema = indicators.ema(daily["close"], ema_period)
        self._alpha = 2 / (ema_period + 1)
        self._period = ema_period

    def bullish(self, t: pd.Timestamp) -> bool:
        j = self._close.index.searchsorted(t, side="left") - 1
        k = self._ema.index.searchsorted(t.floor("D")) - 1
        if j < 0 or k < self._period:
            return True
        price, prev = float(self._close.iloc[j]), float(self._ema.iloc[k])
        return price >= prev + self._alpha * (price - prev)


# --- Señales ---------------------------------------------------------------------------

def head_signals(ins: Instrument, fine: pd.DataFrame, lookback: int) -> list[tuple]:
    """Señales BUY de un símbolo, una por vela cerrada: (hora_cierre, precio, stop, objetivo, atr).
    Se cachean (dependen solo de las velas y de los parámetros)."""
    key = repr((ins.symbol, ins.strategy_name, sorted(ins.strategy_params.items()), ins.timeframe,
                ins.strong_close_filter, ins.strong_close_threshold, lookback, len(fine), str(fine.index[-1])))
    path = CACHE_DIR / f"sig_{hashlib.md5(key.encode()).hexdigest()}.pkl"
    if path.exists():
        return pickle.loads(path.read_bytes())

    tf = pd.Timedelta(pandas_tf(ins.timeframe))
    c = resample(fine, ins.timeframe)
    strategy = build_strategy(ins.strategy_name, ins.strategy_params)
    atr = indicators.atr(c["high"], c["low"], c["close"], 14)
    out: list[tuple] = []
    for i in range(strategy.min_candles, len(c) + 1):
        window = c.iloc[max(0, i - lookback):i]
        signal = strategy.generate_signal(ins.symbol, window)
        if signal.type is not SignalType.BUY:
            continue
        last = window.iloc[-1]
        if ins.strong_close_filter:
            rng = last["high"] - last["low"]
            if rng > 0 and (last["close"] - last["low"]) / rng < ins.strong_close_threshold:
                continue
        out.append((window.index[-1] + tf, float(signal.price), signal.stop_loss,
                    signal.take_profit, float(atr.iloc[i - 1])))
    path.write_bytes(pickle.dumps(out))
    return out


# --- Simulación ------------------------------------------------------------------------

def simulate_head(instruments: list[Instrument], config: Config, start: pd.Timestamp,
                  refresh: bool = False,
                  entry_filter: Callable[[Instrument, pd.Timestamp], bool] | None = None,
                  portfolio_filter: Callable[[Instrument, pd.Timestamp, list[dict]], bool] | None = None,
                  on_close: Callable[[dict], None] | None = None,
                  exposure_on_equity: bool | None = None,
                  size_on_equity: bool = False,
                  ) -> tuple[pd.DataFrame, pd.Series]:
    """Simula un grupo de instrumentos con saldo compartido: una cabeza, o varias a
    la vez (así compiten por el USDT libre y los topes, como en real). Devuelve
    (operaciones, curva de equity cada 4 h) con equity inicial = 1; las entradas
    rechazadas por cabeza y motivo quedan en `equity.attrs["rejected"]`.
    `entry_filter(instrumento, hora)` permite probar filtros de entrada adicionales;
    `portfolio_filter(instrumento, hora, posiciones_abiertas)` lo mismo, pero viendo
    la cartera (cada posición es un dict con al menos `head` y `symbol`).
    `on_close(operación)` se llama al cerrar cada operación (para reglas con memoria,
    p. ej. pausar una cabeza tras varios stops).
    `exposure_on_equity` es la base del tope de exposición (None = lo que diga
    `risk.exposure_on_equity` en el config). `size_on_equity` mide una variante que
    el bot no tiene: dimensionar sobre el equity total en vez de sobre el USDT libre."""
    if exposure_on_equity is None:
        exposure_on_equity = bool(getattr(config.risk, "exposure_on_equity", False))
    fee, slip = config.engine.fee_pct, config.engine.slippage_pct
    since = start - pd.Timedelta(days=WARMUP_DAYS)
    fine = {ins.symbol: candles(ins.symbol, "15m", since, refresh) for ins in instruments}
    # Hasta el último día completo: resultados (y caché de señales) estables durante el día.
    cutoff = min(df.index[-1] for df in fine.values()).floor("D")
    fine = {s: df[df.index < cutoff] for s, df in fine.items()}
    macro = None
    if any(ins.macro_btc_filter for ins in instruments):
        macro = MacroFilter(candles(BTC, "4h", since - pd.Timedelta(days=90), refresh))

    # Filtro de tendencia de la propia moneda (misma media que el motor, vela en formación incluida).
    asset_trend = {ins.symbol: MacroFilter(fine[ins.symbol], ins.asset_trend_ema)
                   for ins in instruments if ins.asset_trend_ema > 0}

    signals_at: dict[pd.Timestamp, list] = {}
    for ins in instruments:
        for t, price, stop, take, atr in head_signals(ins, fine[ins.symbol], config.lookback - 1):
            if t >= start:
                signals_at.setdefault(t, []).append((ins, price, stop, take, atr))

    idx = None
    for df in fine.values():
        idx = df.index if idx is None else idx.union(df.index)
    idx = idx[idx >= start]
    close_time = idx + pd.Timedelta(EXIT_TF)
    arr = {s: {k: df[k].reindex(idx).to_numpy() for k in ("open", "high", "low", "close")} for s, df in fine.items()}
    atr_fine = {}
    for ins in instruments:
        if ins.use_atr_trailing:
            c = fine[ins.symbol].resample(pandas_tf(ins.timeframe)).agg(AGG).dropna()
            a = indicators.atr(c["high"], c["low"], c["close"], 14)
            a.index = a.index + pd.Timedelta(pandas_tf(ins.timeframe))   # disponible al cierre de la vela
            atr_fine[ins.symbol] = a.reindex(idx, method="ffill").to_numpy()

    rejected: dict[str, dict[str, int]] = {}

    def reject(ins: Instrument, why: str) -> None:
        by_head = rejected.setdefault(ins.category, {})
        by_head[why] = by_head.get(why, 0) + 1

    # Reglas de pausa por cabeza (misma lógica que Engine._register_strike).
    head_cfg = {ins.category: ins for ins in instruments}
    strikes: dict[str, list[pd.Timestamp]] = {}
    paused_until: dict[str, pd.Timestamp] = {}
    pauses: dict[str, int] = {}

    def register_strike(trade: dict) -> None:
        ins = head_cfg[trade["head"]]
        if ins.strike_limit <= 0 or trade["pnl"] >= 0 or trade["reason"] not in ("stop-loss", "trailing-stop"):
            return
        head, t = ins.category, trade["closed"]
        if head in paused_until and t < paused_until[head]:
            return
        window = pd.Timedelta(days=ins.strike_window_days)
        recent = [x for x in strikes.get(head, []) if t - x <= window] + [t]
        strikes[head] = recent
        if len(recent) >= ins.strike_limit:
            paused_until[head] = t + pd.Timedelta(days=ins.strike_pause_days)
            pauses[head] = pauses.get(head, 0) + 1
            strikes[head] = []

    cash = 1.0
    positions: list[dict] = []
    trades: list[dict] = []
    eq_t, eq_v = [], []
    last_px = {s: np.nan for s in fine}

    def sell(p: dict, fill: float, amount: float) -> None:
        nonlocal cash
        proceeds = amount * fill * (1 - fee)
        cash += proceeds
        p["realized"] += proceeds
        p["amount"] -= amount

    def close(p: dict, fill: float, t: pd.Timestamp, reason: str) -> None:
        sell(p, fill, p["amount"])
        trades.append(dict(opened=p["opened"], closed=t, head=p["head"], symbol=p["symbol"], reason=reason,
                           ret=p["realized"] / p["cost"] - 1, pnl=p["realized"] - p["cost"],
                           entry=p["entry"], stop=p["stop"]))
        register_strike(trades[-1])
        if on_close is not None:
            on_close(trades[-1])

    for n in range(len(idx)):
        t = close_time[n]
        still_open = []
        for p in positions:
            a = arr[p["symbol"]]
            o, h, low, c = a["open"][n], a["high"][n], a["low"][n], a["close"][n]
            if np.isnan(c):
                still_open.append(p)
                continue
            if low <= p["stop"]:                                   # stop primero (conservador)
                fill = min(o, p["stop"]) * (1 - slip - STOP_SLIPPAGE)
                close(p, fill, t, "trailing-stop" if p["trailing"] else "stop-loss")
                continue
            if p["partial"] > 0 and not p["partial_done"] and h >= p["entry"] * (1 + p["partial"]):
                sell(p, p["entry"] * (1 + p["partial"]) * (1 - slip), p["amount"] * p["partial_ratio"])
                p["partial_done"] = True
                p["stop"] = max(p["stop"], p["entry"])             # stop a breakeven
            if h >= p["take"]:
                close(p, p["take"] * (1 - slip), t, "take-profit")
                continue
            p["peak"] = max(p["peak"], h)
            if p["atr_mult"]:
                v = atr_fine[p["symbol"]][n]
                if not np.isnan(v):
                    p["stop"] = max(p["stop"], p["peak"] - p["atr_mult"] * v)
            elif p["trail_pct"]:
                p["stop"] = max(p["stop"], p["peak"] * (1 - p["trail_pct"]))
            still_open.append(p)
        positions = still_open
        for s in fine:
            c = arr[s]["close"][n]
            if not np.isnan(c):
                last_px[s] = c

        for ins, price, sig_stop, sig_take, atr in signals_at.get(t, ()):
            if any(q["head"] in ins.paused_while_open for q in positions):
                reject(ins, "pausa por otra cabeza")
                continue
            if ins.category in paused_until and t < paused_until[ins.category]:
                reject(ins, "pausa por strikes")
                continue
            if ins.macro_btc_filter and macro is not None and not macro.bullish(t):
                continue
            if ins.symbol in asset_trend and not asset_trend[ins.symbol].bullish(t):
                reject(ins, "tendencia de la moneda")
                continue
            if entry_filter is not None and not entry_filter(ins, t):
                continue
            if portfolio_filter is not None and not portfolio_filter(ins, t, positions):
                reject(ins, "filtro de cartera")
                continue
            if len(positions) >= config.risk.max_open_positions:
                reject(ins, "tope de posiciones")
                continue
            if sum(1 for p in positions if p["symbol"] == ins.symbol) >= ins.max_concurrent_per_symbol:
                reject(ins, "símbolo ocupado")
                continue
            equity_now = cash + sum(p["amount"] * last_px[p["symbol"]] for p in positions)
            capital = (equity_now if size_on_equity else cash) * ins.position_size_pct
            exposure = sum(p["entry"] * p["amount"] for p in positions)
            cap = config.risk.max_total_exposure_pct
            base = equity_now if exposure_on_equity else cash
            if cap < 1.0 and base > 0 and (exposure + capital) / base > cap:
                reject(ins, "tope de exposición")
                continue
            if capital > cash:
                reject(ins, "sin saldo libre")
                continue
            if ins.volatility_sizing and atr > 0:
                factor = ins.volatility_ref_atr_pct / (atr / price)
                capital *= max(ins.volatility_size_min, min(ins.volatility_size_max, factor))
            if capital <= 0:
                continue
            entry = price * (1 + slip)
            cash -= capital
            positions.append(dict(
                symbol=ins.symbol, head=ins.category, opened=t, entry=entry, amount=capital * (1 - fee) / entry, cost=capital,
                stop=sig_stop if sig_stop else entry * (1 - ins.stop_loss_pct),
                take=sig_take if sig_take else entry * (1 + ins.take_profit_pct),
                peak=entry, realized=0.0, partial=ins.partial_take_profit_pct,
                partial_ratio=ins.partial_take_profit_ratio, partial_done=False,
                atr_mult=ins.atr_trailing_mult if ins.use_atr_trailing else 0.0,
                trail_pct=0.0 if ins.use_atr_trailing else ins.trailing_stop_pct,
                trailing=ins.use_atr_trailing or ins.trailing_stop_pct > 0,
            ))

        if t.minute == 0 and t.hour % 4 == 0:
            eq_t.append(t)
            eq_v.append(cash + sum(p["amount"] * last_px[p["symbol"]] for p in positions))

    for p in positions:                                            # mark-to-market final
        close(p, last_px[p["symbol"]], close_time[-1], "abierta")
    columns = ["opened", "closed", "head", "symbol", "reason", "ret", "pnl", "entry", "stop"]
    equity = pd.Series(eq_v, index=eq_t)
    equity.attrs["rejected"] = rejected
    equity.attrs["pauses"] = pauses
    return pd.DataFrame(trades, columns=columns), equity


# --- Informe ---------------------------------------------------------------------------

def _half_year(index: pd.DatetimeIndex) -> pd.Index:
    return index.year.astype(str) + "S" + ((index.month - 1) // 6 + 1).astype(str)


def summary_line(trades: pd.DataFrame, equity: pd.Series) -> str:
    if not len(trades):
        return "sin operaciones"
    gains, losses = trades.pnl[trades.pnl > 0].sum(), -trades.pnl[trades.pnl < 0].sum()
    total = equity.iloc[-1] / equity.iloc[0] - 1
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    pf = gains / losses if losses else float("inf")
    return (f"ops {len(trades)} | acierto {(trades.pnl > 0).mean() * 100:.0f}% | media/op {trades.ret.mean() * 100:+.2f}% | "
            f"PF {pf:.2f} | equity {total * 100:+.1f}% ({((1 + total) ** (1 / years) - 1) * 100:+.1f}%/año) | "
            f"maxDD {(1 - equity / equity.cummax()).max() * 100:.1f}%")


def regime_table(market_monthly: pd.Series, result_monthly: pd.Series, threshold: float = 0.10) -> list[str]:
    """Resultado de la cabeza según lo que hizo SU cesta de monedas cada mes."""
    df = pd.concat([market_monthly.rename("mkt"), result_monthly.rename("res")], axis=1).dropna()
    label = lambda x: "alcista" if x > threshold else ("bajista" if x < -threshold else "lateral")  # noqa: E731
    lines = []
    for name, g in df.groupby(df["mkt"].map(label)):
        lines.append(f"  {name:8} meses {len(g):2d} | cesta {g['mkt'].mean() * 100:+6.1f}%/mes | cabeza {g['res'].mean() * 100:+5.2f}%/mes | "
                     f"meses en positivo {int((g['res'] > 0).sum())}/{len(g)}")
    return lines


def monthly_market(symbols: list[str], start: pd.Timestamp) -> pd.Series:
    rets = []
    for s in symbols:
        d = candles(s, "15m", start - pd.Timedelta(days=WARMUP_DAYS))["close"].resample("1D").last().dropna()
        d = d[d.index >= start]
        rets.append(d.resample("MS").last() / d.resample("MS").first() - 1)
    return pd.concat(rets, axis=1).mean(axis=1)


def print_report(name: str, instruments: list[Instrument], trades: pd.DataFrame, equity: pd.Series,
                 start: pd.Timestamp, show_trades: int) -> None:
    ref = instruments[0]
    print(f"\n==== {name} | {ref.strategy_name} @{ref.timeframe} | {', '.join(i.symbol for i in instruments)}")
    print(f"{equity.index[0].date()} → {equity.index[-1].date()}: {summary_line(trades, equity)}")
    if not len(trades):
        return
    by_sem = trades.groupby(_half_year(pd.DatetimeIndex(trades.opened)))
    parts = []
    for k, e in equity.groupby(_half_year(equity.index)):
        n = len(by_sem.get_group(k)) if k in by_sem.groups else 0
        parts.append(f"{k}: {(e.iloc[-1] / e.iloc[0] - 1) * 100:+.1f}% (n={n})")
    print("por semestre: " + " | ".join(parts))
    print("por símbolo:  " + " | ".join(
        f"{s} n={len(t)} {t.pnl.sum() * 100:+.1f}%" for s, t in trades.groupby("symbol")))
    print("por salida:   " + " | ".join(
        f"{r} n={len(t)} media {t.ret.mean() * 100:+.2f}% suma {t.pnl.sum() * 100:+.1f}%" for r, t in trades.groupby("reason")))
    daily = equity.resample("1D").last().dropna()
    monthly = daily.resample("MS").last() / daily.resample("MS").first() - 1
    print("por tipo de mes (según la cesta de la cabeza):")
    for line in regime_table(monthly_market([i.symbol for i in instruments], start), monthly):
        print(line)
    if show_trades:
        print(f"últimas {show_trades} operaciones:")
        for _, r in trades.sort_values("opened").tail(show_trades).iterrows():
            print(f"  {r.opened:%Y-%m-%d %H:%M} → {r.closed:%m-%d %H:%M} {r.symbol:10} {r.ret * 100:+6.2f}% {r.reason}")


def print_combined(heads: dict[str, list[Instrument]], trades: pd.DataFrame, equity: pd.Series) -> None:
    """Informe de varias cabezas simuladas JUNTAS (compitiendo por el saldo libre)."""
    print(f"\n==== CONJUNTO ({', '.join(heads)}) con saldo compartido")
    print(f"{equity.index[0].date()} → {equity.index[-1].date()}: {summary_line(trades, equity)}")
    print("por semestre: " + " | ".join(
        f"{k}: {(e.iloc[-1] / e.iloc[0] - 1) * 100:+.1f}%" for k, e in equity.groupby(_half_year(equity.index))))
    rejected = equity.attrs.get("rejected", {})
    for name in heads:
        t = trades[trades["head"] == name]
        blocked = ", ".join(f"{n} por {why}" for why, n in rejected.get(name, {}).items()) or "ninguna"
        if equity.attrs.get("pauses", {}).get(name):
            blocked += f" | pausas por strikes: {equity.attrs['pauses'][name]}"
        wins = f"{(t.pnl > 0).mean() * 100:3.0f}%" if len(t) else "  –"
        print(f"  {name:18} ops {len(t):3d} | acierto {wins} | aporta {t.pnl.sum() * 100:+6.1f}% del equity inicial | "
              f"entradas rechazadas: {blocked}")


def fixed_heads(config: Config) -> dict[str, list[Instrument]]:
    heads: dict[str, list[Instrument]] = {}
    for ins in config.instruments:
        if not ins.dynamic_rs_enabled:
            heads.setdefault(ins.category, []).append(ins)
    return heads


def main() -> None:
    parser = argparse.ArgumentParser(description="Simula las cabezas fijas con la mecánica real del bot")
    parser.add_argument("--head", default=None, help="Nombre de la cabeza (def: todas las fijas)")
    parser.add_argument("--start", default="2024-03-01", help="Fecha de inicio (def: 2024-03-01)")
    parser.add_argument("--trades", type=int, default=0, help="Lista las últimas N operaciones")
    parser.add_argument("--refresh", action="store_true", help="Vuelve a descargar las velas")
    parser.add_argument("--combined", action="store_true",
                        help="Simula todas las cabezas JUNTAS, compitiendo por el saldo libre y los topes")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    start = pd.Timestamp(args.start, tz="UTC")
    heads = fixed_heads(config)
    if args.head:
        if args.head not in heads:
            print(f"Cabeza desconocida o con rotación RS: {args.head}. Disponibles: {', '.join(heads)}")
            return
        heads = {args.head: heads[args.head]}
    if args.combined:
        everything = [ins for group in heads.values() for ins in group]
        trades, equity = simulate_head(everything, config, start, refresh=args.refresh)
        print_combined(heads, trades, equity)
        print("\nNota: rendimiento pasado NO garantiza resultados futuros.")
        return
    for name, instruments in heads.items():
        trades, equity = simulate_head(instruments, config, start, refresh=args.refresh)
        print_report(name, instruments, trades, equity, start, args.trades)
    print("\nNota: cada cabeza se simula sola (usa --combined para verlas juntas); "
          "rendimiento pasado NO garantiza resultados futuros.")


if __name__ == "__main__":
    main()
