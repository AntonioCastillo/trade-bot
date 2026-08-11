"""Validación walk-forward de todo el universo contra datos reales de KuCoin.

Para cada símbolo: entrena (elige parámetros de una rejilla) sobre tramos
in-sample y mide el rendimiento en los tramos out-of-sample que NUNCA vio.
Compara IS vs OOS para detectar sobreajuste.

Uso:
    python scripts/walkforward.py             # 2000 velas/símbolo, con grid search
    python scripts/walkforward.py 3000        # nº de velas por símbolo (paginado)
    python scripts/walkforward.py 2000 nogrid # sin optimizar: solo IS vs OOS actuales
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.config import load_config  # noqa: E402
from tradebot.exchange import Exchange  # noqa: E402
from tradebot.factory import setup_logging  # noqa: E402
from tradebot.walkforward import DEFAULT_GRIDS, walk_forward  # noqa: E402


def _verdict(is_ret: float, oos_ret: float, oos_pf: float, oos_trades: int) -> str:
    # Con menos de 5 operaciones OOS no hay muestra suficiente para concluir:
    # cualquier resultado es ruido, no señal.
    if oos_trades < 5:
        return f"MUESTRA INSUFICIENTE ({oos_trades} ops OOS)"
    if oos_ret > 0 and oos_pf > 1:
        return "ROBUSTO (aguanta OOS)"
    if is_ret > 0 >= oos_ret:
        return "SOBREAJUSTE (bueno IS, malo OOS)"
    if oos_ret <= 0:
        return "NO RENTABLE"
    return "DUDOSO"


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    use_grid = not (len(sys.argv) > 2 and sys.argv[2] == "nogrid")
    n_splits = 2

    config = load_config()
    setup_logging("WARNING")
    exchange = Exchange(config)

    print("=" * 78)
    print(f"VALIDACIÓN WALK-FORWARD  |  {limit} velas/símbolo  |  "
          f"{'con grid search' if use_grid else 'sin optimizar (params actuales)'}")
    print("=" * 78)
    print(f"{'símbolo':12} {'tramo':4} {'ops':>4} {'ret%':>8} {'PF':>6} "
          f"{'maxDD%':>7} {'Sharpe':>7}   veredicto")
    print("-" * 78)

    for ins in config.instruments:
        try:
            # Cada cabeza con SU timeframe (no el global): trend1d=1d, volumen5m=5m…
            candles = exchange.fetch_ohlcv_history(ins.symbol, ins.timeframe, limit)
        except Exception as e:
            print(f"{ins.symbol:12} SKIP: {e}")
            continue

        grid = DEFAULT_GRIDS.get(ins.strategy_name) if use_grid else None
        res = walk_forward(candles, ins, config, n_splits=n_splits, param_grid=grid)
        is_m, oos_m = res.is_metrics, res.oos_metrics

        v = _verdict(is_m.return_pct, oos_m.return_pct, oos_m.profit_factor, oos_m.trades)
        pf_is = "inf" if is_m.profit_factor == float("inf") else f"{is_m.profit_factor:.2f}"
        pf_oos = "inf" if oos_m.profit_factor == float("inf") else f"{oos_m.profit_factor:.2f}"

        print(f"{ins.symbol:12} {'IS':4} {is_m.trades:>4} {is_m.return_pct:>+8.2f} "
              f"{pf_is:>6} {is_m.max_drawdown_pct:>7.2f} {is_m.sharpe:>7.2f}")
        print(f"{'':12} {'OOS':4} {oos_m.trades:>4} {oos_m.return_pct:>+8.2f} "
              f"{pf_oos:>6} {oos_m.max_drawdown_pct:>7.2f} {oos_m.sharpe:>7.2f}   {v}")
        print("-" * 78)

    print("\nInterpretación: si el rendimiento OOS se derrumba frente al IS, los")
    print("parámetros están sobreajustados y NO son fiables para operar en real.")


if __name__ == "__main__":
    main()
