"""Simulador con la MECÁNICA REAL del bot para las cabezas con rotación por Fuerza
Relativa (breakout_diario, momentum_diario) y A/B de dos cambios de entrada/salida.

Reproduce lo que hace el daemon en vivo, sobre velas de 4 h:
  - rotación RS cada 4 h (top-K con histéresis, vela diaria en formación incluida);
  - la señal diaria se evalúa cuando el símbolo entra en el bucle, y se compra a
    mercado en ESE turno de 4 h (puede ser horas después del cierre que dio la señal);
  - salidas intradía: stop, parcial + breakeven, objetivo y trailing por ATR.

Variantes medidas:
  - límite de persecución: no entrar si el precio se ha alejado de la señal;
  - stop inicial por ATR, o stop evaluado solo al cierre diario.
Incluye walk-forward anclado: elige la variante en el tramo de entrenamiento y la
mide en el siguiente, nunca visto.

Uso:
    python scripts/livesim_trend.py
    python scripts/livesim_trend.py --start 2025-01-01 --refresh
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from livesim import AGG, BTC, STOP_SLIPPAGE, MacroFilter, candles  # noqa: E402
from tradebot import indicators  # noqa: E402
from tradebot.config import Config, Instrument, load_config  # noqa: E402
from tradebot.models import SignalType  # noqa: E402
from tradebot.relative_strength import select_top_symbols  # noqa: E402
from tradebot.strategy import build_strategy  # noqa: E402

WARMUP_DAYS = 152

CHASE = {
    "sin límite": None,
    "persecución ≤2%": ("pct", 0.02),
    "persecución ≤3%": ("pct", 0.03),
    "persecución ≤5%": ("pct", 0.05),
    "persecución ≤0.25 ATR": ("atr", 0.25),
    "persecución ≤0.5 ATR": ("atr", 0.5),
    "persecución ≤1 ATR": ("atr", 1.0),
}
STOPS = {
    "stop actual": ("pct", None),
    "stop 1.5 ATR": ("atr", 1.5),
    "stop 2 ATR": ("atr", 2.0),
    "stop 2.5 ATR": ("atr", 2.5),
    "stop 3 ATR": ("atr", 3.0),
    "stop actual al cierre diario": ("close", None),
}
BASE = ("sin límite", "stop actual")


class Market:
    """Velas de 4 h alineadas + diarias derivadas, para el pool y BTC."""

    def __init__(self, symbols: list[str], start: pd.Timestamp, refresh: bool):
        since = start - pd.Timedelta(days=WARMUP_DAYS)
        raw = {s: candles(s, "4h", since, refresh) for s in [*symbols, BTC]}
        self.index = raw[BTC].index
        self.n = len(self.index)
        self.first = int(np.searchsorted(self.index, start))
        self.close_time = self.index + pd.Timedelta("4h")
        self.day = self.close_time.floor("D")
        self.arr = {s: {k: df[k].reindex(self.index).to_numpy() for k in ("open", "high", "low", "close")}
                    for s, df in raw.items()}
        self.daily = {s: df.resample("1D").agg(AGG).dropna() for s, df in raw.items()}
        self.macro = MacroFilter(raw[BTC])
        self.atr = {}                               # ATR diario de la última vela cerrada, por barra de 4 h
        for s, d in self.daily.items():
            a = indicators.atr(d["high"], d["low"], d["close"], 14)
            pos = a.index.searchsorted(self.day) - 1
            self.atr[s] = np.where(pos >= 14, a.to_numpy()[np.clip(pos, 0, len(a) - 1)], np.nan)


def entry_candidates(mk: Market, ref: Instrument, universe: list[str], initial: list[str]) -> list[dict]:
    """Entradas que el bot habría evaluado: rotación + señal + filtros actuales.
    No dependen de la variante de entrada/salida."""
    strategy = build_strategy(ref.strategy_name, ref.strategy_params)
    lookback = pd.Timedelta(days=ref.rs_lookback_days + 1)
    selected = list(initial)
    last_closed: dict[str, pd.Timestamp] = {}
    out: list[dict] = []
    for i in range(mk.first, mk.n):
        day, d0 = mk.day[i], mk.day[i] - lookback
        btc_close = mk.daily[BTC]["close"]
        if d0 not in btc_close.index:
            continue
        btc_ret = mk.arr[BTC]["close"][i] / btc_close.loc[d0] - 1
        ranking = {}
        for s in universe:
            price, daily = mk.arr[s]["close"][i], mk.daily[s]
            if np.isnan(price) or d0 not in daily.index or daily.index.searchsorted(day) < 45:
                continue
            ranking[s] = (price / daily["close"].loc[d0] - 1 - btc_ret) * 100
        ranking = dict(sorted(ranking.items(), key=lambda kv: -kv[1]))
        selected = select_top_symbols([s for s in selected if s in ranking], ranking,
                                      top_k=ref.rs_top_k, hysteresis_pct=ref.rs_hysteresis_pct)
        closed_day = day - pd.Timedelta("1D")
        for s in selected:
            if last_closed.get(s) == closed_day:        # una evaluación por vela diaria cerrada
                continue
            last_closed[s] = closed_day
            d = mk.daily[s].loc[:closed_day].iloc[-300:]
            if len(d) < strategy.min_candles or d.index[-1] != closed_day:
                continue
            if strategy.generate_signal(s, d).type is not SignalType.BUY:
                continue
            last = d.iloc[-1]
            if ref.strong_close_filter:
                rng = last["high"] - last["low"]
                if rng > 0 and (last["close"] - last["low"]) / rng < ref.strong_close_threshold:
                    continue
            if ref.macro_btc_filter and not mk.macro.bullish(mk.close_time[i]):
                continue
            signal, price = float(last["close"]), mk.arr[s]["close"][i]
            out.append(dict(i=i, symbol=s, signal=signal, price=price, atr=mk.atr[s][i], chase=price / signal - 1))
    return out


def simulate_position(mk: Market, ref: Instrument, cost: float, c: dict, stop_mode: str, stop_k: float | None):
    """Devuelve (retorno neto de la posición, barra de salida, motivo)."""
    a, atr_bar, entry = mk.arr[c["symbol"]], mk.atr[c["symbol"]], c["price"]
    stop = entry - stop_k * c["atr"] if stop_mode == "atr" else entry * (1 - ref.stop_loss_pct)
    take, partial = entry * (1 + ref.take_profit_pct), ref.partial_take_profit_pct
    buy = entry * (1 + cost)
    peak, remaining, pnl, partial_done = entry, 1.0, 0.0, partial <= 0
    for j in range(c["i"] + 1, mk.n):
        o, h, low, close = a["open"][j], a["high"][j], a["low"][j], a["close"][j]
        if np.isnan(close):
            continue
        intraday = stop_mode != "close" or (partial > 0 and partial_done)   # tras la parcial, el breakeven es intradía
        if intraday and low <= stop:
            fill = min(o, stop) * (1 - STOP_SLIPPAGE)
            return pnl + remaining * (fill * (1 - cost) / buy - 1), j, "stop"
        if not partial_done and h >= entry * (1 + partial):
            ratio = ref.partial_take_profit_ratio
            pnl += ratio * (entry * (1 + partial) * (1 - cost) / buy - 1)
            remaining -= ratio
            partial_done = True
            stop = max(stop, entry)
        if h >= take:
            return pnl + remaining * (take * (1 - cost) / buy - 1), j, "objetivo"
        if not intraday and mk.close_time[j] == mk.day[j] and close <= stop:
            return pnl + remaining * (close * (1 - cost) / buy - 1), j, "stop al cierre"
        peak = max(peak, h)
        if ref.use_atr_trailing and not np.isnan(atr_bar[j]):
            stop = max(stop, peak - ref.atr_trailing_mult * atr_bar[j])
        elif ref.trailing_stop_pct > 0:
            stop = max(stop, peak * (1 - ref.trailing_stop_pct))
    return pnl + remaining * (a["close"][mk.n - 1] * (1 - cost) / buy - 1), mk.n - 1, "abierta"


def run_variant(mk: Market, ref: Instrument, cost: float, cands: list[dict], chase, stop) -> pd.DataFrame:
    busy: dict[str, int] = {}
    rows = []
    for c in cands:
        if busy.get(c["symbol"], -1) >= c["i"]:          # una posición por símbolo
            continue
        if chase:
            limit = chase[1] if chase[0] == "pct" else chase[1] * c["atr"] / c["signal"]
            if c["chase"] > limit:
                continue
        ret, j, reason = simulate_position(mk, ref, cost, c, *stop)
        size = ref.position_size_pct
        if ref.volatility_sizing and c["atr"] > 0:
            factor = ref.volatility_ref_atr_pct / (c["atr"] / c["signal"])
            size *= max(ref.volatility_size_min, min(ref.volatility_size_max, factor))
        busy[c["symbol"]] = j
        rows.append(dict(opened=mk.close_time[c["i"]], symbol=c["symbol"], ret=ret, contrib=size * ret,
                         reason=reason, chase=c["chase"]))
    return pd.DataFrame(rows, columns=["opened", "symbol", "ret", "contrib", "reason", "chase"])


def stats_line(name: str, t: pd.DataFrame) -> str:
    if not len(t):
        return f"{name:30} sin operaciones"
    gains, losses = t["contrib"][t["contrib"] > 0].sum(), -t["contrib"][t["contrib"] < 0].sum()
    cum = t["contrib"].cumsum()
    pf = gains / losses if losses else float("inf")
    return (f"{name:30} n={len(t):3d} acierto {(t['ret'] > 0).mean() * 100:3.0f}%  media/pos {t['ret'].mean() * 100:+5.2f}%  "
            f"equity {t['contrib'].sum() * 100:+6.1f}%  PF {pf:4.2f}  maxDD {(cum.cummax() - cum).clip(lower=0).max() * 100:4.1f}%")


def report_head(mk: Market, name: str, ref: Instrument, cost: float, universe: list[str],
                universe_name: str, initial: list[str], n_splits: int = 3) -> None:
    cands = entry_candidates(mk, ref, universe, initial)
    print(f"\n######## {name} ({ref.strategy_name}) | {universe_name} | "
          f"{mk.index[mk.first].date()} → {mk.index[-1].date()} | entradas candidatas {len(cands)}")
    if not cands:
        return
    chase = pd.Series([c["chase"] for c in cands])
    print(f"distancia entrada–señal: nula en {int((chase.abs() < 1e-9).sum())}; >2% en {int((chase > .02).sum())}; "
          f">5% en {int((chase > .05).sum())}; máx {chase.max() * 100:.1f}%")
    res = {(a, b): run_variant(mk, ref, cost, cands, CHASE[a], STOPS[b]) for a in CHASE for b in STOPS}
    base = res[BASE]
    print("-- un cambio cada vez --")
    for a in CHASE:
        print(stats_line(a, res[(a, BASE[1])]))
    for b in list(STOPS)[1:]:
        print(stats_line(b, res[(BASE[0], b)]))
    print("-- configuración actual, según la distancia a la señal --")
    print(stats_line("  entradas a ≤2% de la señal", base[base.chase <= 0.02]))
    print(stats_line("  entradas a >2% de la señal", base[base.chase > 0.02]))

    t0, t1 = mk.index[mk.first], mk.index[-1]
    mid = t0 + (t1 - t0) * 0.5
    step = (t1 - mid) / n_splits
    chosen, current = [], []
    print(f"-- walk-forward anclado ({n_splits} tramos fuera de muestra) --")
    for k in range(n_splits):
        lo = mid + step * k
        hi = mid + step * (k + 1) if k < n_splits - 1 else t1 + pd.Timedelta("1D")

        def in_sample(variant) -> float:
            t = res[variant]
            t = t[t.opened < lo]
            return t["contrib"].sum() if len(t) >= 10 else float("-inf")

        best = max(res, key=in_sample)
        oos = res[best][(res[best].opened >= lo) & (res[best].opened < hi)]
        oos_base = base[(base.opened >= lo) & (base.opened < hi)]
        chosen.append(oos)
        current.append(oos_base)
        print(f"tramo {k + 1} {lo.date()} → {min(hi, t1).date()}: elegida = {best[0]} + {best[1]} | "
              f"elegida {oos['contrib'].sum() * 100:+.1f}% (n={len(oos)}) vs actual {oos_base['contrib'].sum() * 100:+.1f}% (n={len(oos_base)})")
    print(stats_line("fuera de muestra: elegida", pd.concat(chosen)))
    print(stats_line("fuera de muestra: actual", pd.concat(current)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Simula las cabezas con rotación RS con la mecánica real del bot")
    parser.add_argument("--start", default="2024-03-01", help="Fecha de inicio (def: 2024-03-01)")
    parser.add_argument("--refresh", action="store_true", help="Vuelve a descargar las velas")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config: Config = load_config(args.config)
    heads: dict[str, list[Instrument]] = {}
    for ins in config.instruments:
        if ins.dynamic_rs_enabled:
            heads.setdefault(ins.category, []).append(ins)
    if not heads:
        print("No hay cabezas con rs_selection activado en la configuración.")
        return
    fixed = {ins.symbol for ins in config.instruments if not ins.dynamic_rs_enabled}
    pool = sorted({s for group in heads.values() for s in group[0].rs_pool})
    cost = config.engine.fee_pct + config.engine.slippage_pct
    mk = Market(pool, pd.Timestamp(args.start, tz="UTC"), args.refresh)

    for name, group in heads.items():
        ref = group[0]
        head_pool = [s for s in ref.rs_pool if s in mk.daily]
        initial = [ins.symbol for ins in group]
        report_head(mk, name, ref, cost, head_pool, f"pool completo ({len(head_pool)})", initial)
        free = [s for s in head_pool if s not in fixed]
        report_head(mk, name, ref, cost, free, f"sin símbolos de cabezas fijas ({len(free)})", initial)
    print("\nNota: tamaños sin interés compuesto; rendimiento pasado NO garantiza resultados futuros.")


if __name__ == "__main__":
    main()
