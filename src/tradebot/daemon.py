"""Runner autónomo y desatendido.

Un único bucle que se ocupa de todo sin intervención:
  - Recorre el universo cada `poll_interval_seconds`.
  - Nunca muere por un error puntual (captura y continúa).
  - Reinicia el cortafuegos de pérdida diaria al cambiar el día UTC.
  - Vuelca un informe a disco cada `report_interval_seconds`.

Pensado para lanzarse con `python scripts/run.py` y olvidarse.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .carry import CarryRunner
from .config import Config, load_config
from .engine import Engine
from .exchange import Exchange
from .factory import build_engine
from .notifier import Notifier
from .reporting import render_report
from .selfcheck import run_api_check
from .status import write_status
from .sniper import Sniper
from .storage import Storage

logger = logging.getLogger(__name__)

DEFAULT_LOG_FILE = "logs/tradebot.log"
DEFAULT_REPORT_FILE = "data/report.txt"

# Publicación automática del status a un gist secreto (cada 15 min, desde el bot).
GIST_ID_FILE = "data/.gist_id"
PUBLISH_INTERVAL_SECONDS = 900

# Verificación de API en el PRIMER arranque live (solo una vez).
API_CHECK_MARKER = "data/.api_verified"
API_CHECK_SYMBOL = "BTC/USDT"
API_CHECK_USD = 1.0


def write_report_snapshot(
    storage: Storage, quote: str, path: str, starting_balance: float = 10_000.0
) -> str:
    """Genera el informe y lo guarda en disco. Devuelve el texto generado."""
    text = render_report(storage, quote=quote, starting_balance=starting_balance)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text


def _heads_summary(config: Config) -> str:
    """Lista legible de las cabezas activas (para el arranque y el heartbeat)."""
    from collections import OrderedDict

    groups: "OrderedDict[str, list[str]]" = OrderedDict()
    for ins in config.instruments:
        groups.setdefault(ins.category, []).append(ins.symbol.split("/")[0])
    lines = [f"• {cat}: {', '.join(syms)}" for cat, syms in groups.items()]
    if config.sniper.enabled:
        lines.append("• sniper (recién listadas)")
    if config.carry.enabled:
        lines.append("• carry (funding)")
    return "\n".join(lines) if lines else "(ninguna)"


def _maybe_start_sniper(config: Config, notifier: Notifier) -> threading.Thread | None:
    """Si el sniper está activado, lo arranca en un hilo del MISMO proceso, para
    que todo corra en una sola ventana. Usa su propio cliente de exchange."""
    if not config.sniper.enabled:
        return None
    live = config.mode == "live"
    sniper = Sniper(config, Exchange(config), notifier, live=live)
    thread = threading.Thread(target=sniper.run_forever, name="sniper", daemon=True)
    thread.start()
    logger.info("Sniper lanzado en segundo plano (mismo proceso) | modo=%s",
                "LIVE" if live else "PAPER")
    return thread


def _notify_alive(engine: Engine, config: Config) -> None:
    """Señal de vida periódica a Telegram: confirma que el bot sigue en marcha."""
    s = engine.storage.summary()
    try:
        eq = f"{engine.equity():.2f} {config.risk.quote_currency}"
    except Exception:
        eq = "n/d"
    engine.notifier.notify(
        f"💓 <b>Bot activo</b>\n"
        f"Equity: {eq}\n"
        f"Operaciones: {s['trades']} | P&L {s['pnl_abs']:+.2f} {config.risk.quote_currency}\n"
        f"Estado: {'OPERANDO' if not engine.risk.halted else 'DETENIDO (límite diario)'}\n"
        f"<b>Cabezas activas:</b>\n{_heads_summary(config)}"
    )


def _maybe_start_carry(config: Config, notifier: Notifier) -> threading.Thread | None:
    """Si el carry está activado, lo arranca en un hilo del mismo proceso (PAPER).
    Usa su propio cliente de exchange y su propio balance simulado."""
    if not config.carry.enabled:
        return None
    runner = CarryRunner(config, Exchange(config), notifier)
    thread = threading.Thread(target=runner.run_forever, name="carry", daemon=True)
    thread.start()
    # El propio runner ya loguea si es PAPER, DRY-RUN o REAL según config+confirmación.
    logger.info("Carry (funding) lanzado en segundo plano (mismo proceso)")
    return thread


def _maybe_start_publisher(config: Config, engine: Engine) -> threading.Thread | None:
    """Publica el status a un gist secreto cada PUBLISH_INTERVAL_SECONDS, en un hilo
    del PROPIO bot (no hace falta cron ni timer). Resiliente: si GitHub falla, el bot
    sigue. Recuerda el gist id en data/.gist_id, así los reinicios actualizan el mismo
    gist sin tocar el .env. Se activa solo si hay GITHUB_TOKEN en el entorno."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        logger.info("Sin GITHUB_TOKEN: el bot no publicará el status (opcional).")
        return None

    def _read_gist_id() -> str | None:
        gid = os.environ.get("TRADEBOT_GIST_ID", "").strip()
        if gid:
            return gid
        p = Path(GIST_ID_FILE)
        return p.read_text(encoding="utf-8").strip() if p.exists() else None

    def _loop() -> None:
        from .publisher import publish_to_gist
        from .status import build_status, merge_sniper
        gist_id = _read_gist_id()
        notified = False
        while True:
            try:
                status = merge_sniper(build_status(engine, config))
                res = publish_to_gist(status, token, gist_id)
                if res["created"]:
                    gist_id = res["id"]
                    try:
                        Path(GIST_ID_FILE).parent.mkdir(parents=True, exist_ok=True)
                        Path(GIST_ID_FILE).write_text(gist_id, encoding="utf-8")
                    except Exception:
                        logger.warning("No pude guardar %s", GIST_ID_FILE)
                if not notified:
                    engine.notifier.notify(
                        f"📡 <b>Status publicándose</b> (cada {PUBLISH_INTERVAL_SECONDS // 60} min)\n"
                        f"URL: {res['raw_url']}")
                    logger.info("Status publicado en: %s", res["raw_url"])
                    notified = True
            except Exception:
                logger.exception("Fallo publicando el status; reintento en el próximo ciclo")
            time.sleep(PUBLISH_INTERVAL_SECONDS)

    thread = threading.Thread(target=_loop, name="publisher", daemon=True)
    thread.start()
    logger.info("Publicador de status lanzado (cada %ds)", PUBLISH_INTERVAL_SECONDS)
    return thread


def _maybe_first_run_api_check(engine: Engine, config: Config) -> None:
    """En el PRIMER arranque en modo live, hace una verificación real de ~1 USD
    (compra+venta). Deja una marca en disco para no repetirla nunca más."""
    if config.mode != "live":
        return
    marker = Path(API_CHECK_MARKER)
    if marker.exists():
        logger.info("API ya verificada anteriormente (%s); no se repite.", marker)
        return
    logger.info("Primer arranque live: verificando API con %.2f %s…",
                API_CHECK_USD, config.risk.quote_currency)
    try:
        run_api_check(
            engine.exchange, API_CHECK_SYMBOL, API_CHECK_USD,
            config.risk.quote_currency, engine.notifier,
        )
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        logger.info("API verificada correctamente; no se repetirá.")
    except Exception:
        logger.exception("Falló la verificación de API en el primer arranque")
        engine.notifier.notify(
            "⚠️ <b>Verificación de API FALLÓ</b> en el primer arranque. "
            "Revisa claves/permisos antes de confiar en el bot."
        )


def _live_preflight(engine: Engine, config: Config, symbols: list[str]) -> None:
    """En modo live, avisa qué símbolos no llegan al mínimo de orden de KuCoin
    con el tamaño de posición actual (balance × position_size_pct)."""
    try:
        balance = engine.execution.get_balance()
    except Exception:
        logger.exception("No pude leer el balance real para el preflight")
        return
    logger.info("Preflight LIVE | balance real: %.2f %s", balance, config.risk.quote_currency)
    for symbol in symbols:
        ins = config.instrument(symbol)
        planned = balance * ins.position_size_pct
        try:
            limits = engine.exchange.market_limits(symbol)
        except Exception:
            logger.warning("[%s] no pude leer límites del mercado", symbol)
            continue
        min_cost = limits.get("min_cost")
        if min_cost and planned < min_cost:
            logger.warning(
                "[%s] posición prevista %.2f %s < mínimo %.2f -> se RECHAZARÁN sus órdenes",
                symbol, planned, config.risk.quote_currency, min_cost,
            )
        else:
            logger.info(
                "[%s] posición prevista %.2f %s (mínimo %s) OK",
                symbol, planned, config.risk.quote_currency, min_cost,
            )


def _validate_symbols(engine: Engine, symbols: list[str]) -> list[str]:
    """Filtra el universo a los símbolos que el exchange ofrece de verdad.
    Si no se pueden cargar los mercados (red), sigue con lo configurado."""
    try:
        available = engine.exchange.market_symbols()
    except Exception:
        logger.exception("No se pudieron cargar los mercados; uso el universo tal cual")
        return symbols
    valid = [s for s in symbols if s in available]
    invalid = [s for s in symbols if s not in available]
    if invalid:
        logger.warning("Símbolos no disponibles en el exchange (se ignoran): %s", invalid)
    return valid


def run_forever(
    config: Config | None = None,
    engine: Engine | None = None,
    report_path: str = DEFAULT_REPORT_FILE,
    log_file: str = DEFAULT_LOG_FILE,
) -> None:
    config = config or load_config()
    engine = engine or build_engine(config, log_file=log_file)

    symbols = _validate_symbols(engine, config.symbols())
    if not symbols:
        logger.error("Ningún símbolo del universo es válido en el exchange. Abortando.")
        return
    if config.mode == "live":
        _live_preflight(engine, config, symbols)

    # Readopta las posiciones abiertas persistidas (reinicio seguro): en vez de
    # dejarlas huérfanas, el motor sigue gestionando su SL/TP/trailing.
    try:
        engine.load_positions()
    except Exception:
        logger.exception("No pude readoptar posiciones persistidas al arrancar")

    interval = config.engine.poll_interval_seconds
    report_interval = config.engine.report_interval_seconds
    current_day = datetime.now(timezone.utc).date()
    last_report = 0.0
    last_alive = time.time()
    prev_halted = False
    err_state = {"last": 0.0}
    last_closed: dict[str, object] = {}   # última vela CERRADA procesada por símbolo

    def _notify_fail(prefix: str, exc: Exception) -> None:
        """Avisa por Telegram de un fallo, con anti-spam por tiempo."""
        now = time.time()
        if now - err_state["last"] >= config.engine.error_notify_interval_seconds:
            engine.notifier.notify(f"⚠️ <b>Fallo</b> {prefix}\n{type(exc).__name__}: {exc}")
            err_state["last"] = now

    logger.info(
        "Daemon iniciado | modo=%s | %d símbolos | ciclo=%ds | informe=%ds | log=%s",
        config.mode.upper(), len(symbols), interval, report_interval, log_file,
    )
    try:
        balance_txt = f"{engine.equity():.2f} {config.risk.quote_currency}"
    except Exception:
        balance_txt = "n/d (no se pudo leer)"
    engine.notifier.notify(
        f"🤖 <b>Bot iniciado</b> ({config.mode.upper()})\n"
        f"<b>Cabezas activas:</b>\n{_heads_summary(config)}\n"
        f"Ciclo {interval}s  |  Balance: {balance_txt}"
    )
    _maybe_first_run_api_check(engine, config)
    _maybe_start_sniper(config, engine.notifier)
    _maybe_start_carry(config, engine.notifier)
    _maybe_start_publisher(config, engine)

    # Fija el cortafuegos de pérdida diaria contra el equity REAL de arranque
    # (en live es el balance de la cuenta, no el starting_balance del config).
    try:
        engine.risk.reset_day(engine.equity())
    except Exception:
        logger.warning("No pude fijar el equity inicial para el cortafuegos diario")

    try:
        while True:
            try:
                now = datetime.now(timezone.utc)

                # Nuevo día UTC: reinicia el límite de pérdida diaria y sigue.
                if now.date() != current_day:
                    current_day = now.date()
                    engine.risk.reset_day(engine.equity())
                    logger.info("Nuevo día UTC (%s): cortafuegos diario reiniciado", current_day)

                # Un ciclo sobre todo el universo (cada símbolo aislado).
                for symbol in symbols:
                    try:
                        tf = config.instrument(symbol).timeframe
                        candles = engine.exchange.fetch_ohlcv(
                            symbol, tf, config.lookback
                        )
                        if len(candles) < 2:
                            continue
                        # Decidir solo sobre velas CERRADAS (descarta la vela en
                        # formación) y UNA vez por vela, como el backtest. Evita
                        # re-disparar la misma señal en cada sondeo de 60s.
                        closed = candles.iloc[:-1]
                        ts = closed.index[-1]
                        if last_closed.get(symbol) == ts:
                            continue
                        last_closed[symbol] = ts
                        engine.process(symbol, closed)
                    except Exception as exc:
                        logger.exception("[%s] error en el ciclo; continúo", symbol)
                        _notify_fail(f"en {symbol}", exc)

                # Aviso si se activa el cortafuegos de pérdida diaria (una vez).
                if engine.risk.halted and not prev_halted:
                    engine.notifier.notify(
                        "⚠️ <b>Límite de pérdida diaria alcanzado</b>.\n"
                        "El bot deja de abrir posiciones hasta mañana."
                    )
                prev_halted = engine.risk.halted

                # Señal de vida periódica a Telegram.
                if time.time() - last_alive >= config.engine.alive_interval_seconds:
                    _notify_alive(engine, config)
                    last_alive = time.time()

                # Informe periódico a disco + resumen en el log.
                if time.time() - last_report >= report_interval:
                    write_report_snapshot(
                        engine.storage, config.risk.quote_currency, report_path,
                        config.risk.starting_balance,
                    )
                    try:
                        write_status(engine, config)   # data/status.json (para publicar)
                    except Exception:
                        logger.warning("No pude escribir data/status.json")
                    s = engine.storage.summary()
                    logger.info(
                        "Informe actualizado (%s) | ops=%d | P&L=%.2f %s | equity=%.2f | %s",
                        report_path, s["trades"], s["pnl_abs"],
                        config.risk.quote_currency, engine.equity(),
                        "OPERANDO" if not engine.risk.halted else "DETENIDO (límite diario)",
                    )
                    last_report = time.time()

            except Exception as exc:
                # Cualquier fallo inesperado del bucle: log, avisa y seguimos vivos.
                logger.exception("Error inesperado en el bucle principal; continúo")
                _notify_fail("en el bucle principal", exc)

            time.sleep(interval)

    except KeyboardInterrupt:
        logger.info("Interrumpido por el usuario. Guardando informe final y cerrando.")
    finally:
        try:
            engine.notifier.notify("🛑 <b>Bot detenido</b>")
        except Exception:
            pass
        write_report_snapshot(
            engine.storage, config.risk.quote_currency, report_path,
            config.risk.starting_balance,
        )
        engine.storage.close()
