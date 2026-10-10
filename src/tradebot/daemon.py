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
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .carry import CarryRunner
from .config import Config, load_config
from .engine import Engine
from .exchange import Exchange
from .factory import build_engine
from .funding_radar import evaluate_funding_radar
from .notifier import Notifier
from .reporting import render_report
from .scheduler import EventScheduler
from .selfcheck import run_api_check
from .status import write_status
from .sniper import Sniper
from .storage import Storage
from .telegram_views import (
    render_daily_report_telegram,
    render_heads_summary,
    render_rs_rotations,
    render_welcome_message,
)

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
    """Alias de compatibilidad hacia render_heads_summary."""
    return render_heads_summary(config)


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


def _maybe_evaluate_rs(engine: Engine, config: Config, notify: bool = True) -> None:
    """Evalúa la Fuerza Relativa (RS vs BTC) para las cabezas que tengan dynamic_rs_enabled=True."""
    from collections import OrderedDict
    from .relative_strength import compute_rs_rankings, select_top_symbols

    categories: "OrderedDict[str, Any]" = OrderedDict()
    for ins in config.instruments:
        if getattr(ins, "dynamic_rs_enabled", False):
            categories.setdefault(ins.category, ins)

    if not categories:
        return

    rotations: list[dict[str, Any]] = []
    rankings_cache: dict[tuple, dict[str, float]] = {}

    for cat_name, ins in categories.items():
        try:
            pool = tuple(ins.rs_pool) if ins.rs_pool else ()
            if pool not in rankings_cache:
                rankings_cache[pool] = compute_rs_rankings(
                    engine.exchange, pool=ins.rs_pool or None, benchmark_symbol="BTC/USDT",
                    lookback_days=ins.rs_lookback_days, timeframe="1d"
                )
            rankings = rankings_cache[pool]
            if not rankings:
                continue
            curr_syms = [i.symbol for i in config.instruments if i.category == cat_name]
            new_syms = select_top_symbols(
                curr_syms, rankings, top_k=ins.rs_top_k, hysteresis_pct=ins.rs_hysteresis_pct
            )
            if set(new_syms) != set(curr_syms):
                logger.info(
                    "[RS-ROTACION] [%s] Nuevos símbolos seleccionados: %s (antes: %s)",
                    cat_name, new_syms, curr_syms
                )
                engine.update_head_symbols(cat_name, new_syms)
                rotations.append({
                    "category": cat_name,
                    "new_syms": new_syms,
                    "old_syms": curr_syms,
                })
        except Exception:
            logger.exception("[RS-ROTACION] Fallo al evaluar RS para la cabeza %s", cat_name)

    if notify and rotations:
        engine.notifier.notify(render_rs_rotations(rotations))


def _notify_alive(engine: Engine, config: Config) -> None:
    """Señal de vida periódica a Telegram con informe completo de estado."""
    try:
        report_text = render_daily_report_telegram(engine, config)
        engine.notifier.notify(report_text)
    except Exception:
        logger.exception("Fallo al enviar el informe de estado a Telegram")


def _maybe_start_carry(config: Config, notifier: Notifier, engine: Engine | None = None) -> threading.Thread | None:
    """Si el carry está activado, lo arranca en un hilo del mismo proceso (PAPER o REAL).
    Usa su propio cliente de exchange y su propio balance simulado."""
    if not config.carry.enabled:
        return None
    runner = CarryRunner(config, Exchange(config), notifier, storage=engine.storage if engine else None)
    if engine is not None:
        engine.carry_runner = runner
    thread = threading.Thread(target=runner.run_forever, name="carry", daemon=True)
    thread.start()
    # El propio runner ya loguea si es PAPER, DRY-RUN o REAL según config+confirmación.
    logger.info("Carry (funding) lanzado en segundo plano (mismo proceso)")
    return thread


def _refresh_status(engine: Engine, config: Config) -> bool:
    """Reescribe data/status_<slot>.json con el estado actual. Se llama en cada ciclo
    desde el hilo principal, para que el publicador suba siempre un status reciente."""
    try:
        write_status(engine, config)
        return True
    except Exception:
        logger.warning("No pude escribir el status", exc_info=True)
        return False


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
        from .status import load_unified
        gist_id = _read_gist_id()
        notified = False
        while True:
            try:
                # Solo sube el fichero: el status lo escribe el hilo principal en cada
                # ciclo (`_refresh_status`). Construirlo aquí falla siempre, porque la
                # conexión SQLite pertenece al hilo principal.
                status = load_unified()
                if status.get("instances"):
                    res = publish_to_gist(status, token, gist_id)
                    if res.get("created"):
                        gist_id = res["id"]
                        try:
                            Path(GIST_ID_FILE).parent.mkdir(parents=True, exist_ok=True)
                            Path(GIST_ID_FILE).write_text(gist_id, encoding="utf-8")
                        except Exception:
                            logger.warning("No pude guardar %s", GIST_ID_FILE)
                    if not notified and "raw_url" in res:
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


def _maybe_start_xsmom(config: Config, notifier: Notifier) -> threading.Thread | None:
    """Si está activado, arranca el momentum transversal en un hilo (PAPER)."""
    if not config.xsmom.enabled:
        return None
    from .xsmom import XSMomRunner
    runner = XSMomRunner(config, Exchange(config), notifier)
    thread = threading.Thread(target=runner.run_forever, name="xsmom", daemon=True)
    thread.start()
    logger.info("XS-Momentum lanzado en segundo plano (mismo proceso) | PAPER")
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


class _GracefulStop:
    """Parada ordenada ante SIGTERM (`systemctl stop/restart`, despliegue automático).

    Si el bot está durmiendo entre ciclos, sale al momento. Si está a mitad de ciclo
    (puede haber una orden enviada y aún sin registrar), termina ese trabajo y sale
    en la siguiente espera. La salida usa el mismo camino que Ctrl+C."""

    def __init__(self, sleep=None):
        self._sleep = sleep                   # None = time.sleep, resuelto al dormir
        self.requested = False
        self._sleeping = False

    def install(self) -> bool:
        if threading.current_thread() is not threading.main_thread():
            return False                      # las señales solo se atienden en el hilo principal
        try:
            signal.signal(signal.SIGTERM, self._on_signal)
        except (ValueError, OSError, AttributeError):
            return False
        return True

    def _on_signal(self, signum, frame) -> None:
        # Sin logs aquí: el manejador puede interrumpir una escritura de log a medias.
        self.requested = True
        if self._sleeping:
            raise KeyboardInterrupt

    def sleep(self, seconds: float) -> None:
        if self.requested:
            raise KeyboardInterrupt
        self._sleeping = True
        try:
            (self._sleep or time.sleep)(seconds)
        finally:
            self._sleeping = False
        if self.requested:
            raise KeyboardInterrupt


def _poll_open_exits(engine: Engine, candles_cache: dict) -> None:
    """Sondeo rápido: UNA consulta de precios para las posiciones abiertas y evaluación
    de sus salidas (stop / parcial / objetivo / trailing). No abre posiciones."""
    symbols = list(dict.fromkeys(p.symbol for p in engine.positions))
    if not symbols:
        return
    prices = engine.exchange.fetch_last_prices(symbols)
    for symbol in symbols:
        price = prices.get(symbol)
        if not price or price <= 0:
            continue
        engine.last_prices[symbol] = price
        engine._check_exits(symbol, price, candles=candles_cache.get(symbol), count_bar=False)


def _wait_cycle(engine: Engine, interval: float, exit_poll_seconds: float, candles_cache: dict,
                sleep=time.sleep, clock=time.monotonic) -> None:
    """Espera `interval` hasta el siguiente ciclo. Si el sondeo rápido está activo y hay
    posiciones abiertas, comprueba sus salidas cada `exit_poll_seconds` en vez de dormir
    de un tirón. Un fallo del sondeo no rompe el bucle ni lo detiene: se pierde solo
    ese sondeo y el siguiente se hace a su hora (KuCoin rechaza alguno de vez en cuando,
    y más cuando el mercado se mueve, que es cuando más falta hace vigilar)."""
    if exit_poll_seconds <= 0:
        sleep(interval)
        return
    deadline = clock() + interval
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            return
        if not engine.positions:
            sleep(remaining)
            return
        sleep(min(exit_poll_seconds, remaining))
        if clock() >= deadline:
            return
        try:
            _poll_open_exits(engine, candles_cache)
        except Exception as exc:
            logger.warning("Sondeo rápido de salidas falló (%s); sigo con el siguiente", exc)


def _live_preflight(engine: Engine, config: Config, symbols: list[str]) -> None:
    """En modo live, avisa qué símbolos no llegan al mínimo de orden de KuCoin
    con el tamaño de posición actual (balance * position_size_pct)."""
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
        logger.warning("Universo de engine vacío; corro solo los subsistemas (xsmom/sniper/carry).")
    if config.mode == "live":
        _live_preflight(engine, config, symbols)

    # Readopta las posiciones abiertas persistidas (reinicio seguro): en vez de
    # dejarlas huérfanas, el motor sigue gestionando su SL/TP/trailing.
    try:
        engine.load_positions()
    except Exception:
        logger.exception("No pude readoptar posiciones persistidas al arrancar")

    # En LIVE, ancla el starting_balance al saldo REAL del exchange la PRIMERA vez
    # (y lo persiste): así el % de retorno del informe/status es coherente con el
    # dinero real y no se resetea en cada reinicio. En paper se usa el del config.
    if config.mode == "live":
        ref = engine.storage.get_state("live_starting_balance")
        if ref is None:
            try:
                ref = engine.equity()
                engine.storage.set_state("live_starting_balance", ref)
                logger.info("Starting_balance anclado al saldo real de arranque: %.2f %s",
                            ref, config.risk.quote_currency)
            except Exception:
                logger.warning("No pude leer el saldo real para anclar el starting_balance")
                ref = None
        if ref is not None:
            config.risk.starting_balance = ref

    interval = config.engine.poll_interval_seconds
    report_interval = config.engine.report_interval_seconds
    scheduler = EventScheduler(
        report_interval_seconds=report_interval,
        alive_interval_seconds=config.engine.alive_interval_seconds,
        error_notify_interval_seconds=config.engine.error_notify_interval_seconds,
    )
    prev_halted = False
    last_closed: dict[str, object] = {}   # última vela CERRADA procesada por símbolo
    candles_cache: dict[str, object] = {}  # últimas velas por símbolo (ATR del sondeo rápido)
    exit_poll = config.engine.exit_poll_seconds
    if exit_poll > 0:
        logger.info("Sondeo rápido de salidas activo: posiciones abiertas cada %ds", exit_poll)

    def _notify_fail(prefix: str, exc: Exception) -> None:
        """Avisa por Telegram de un fallo, con anti-spam por tiempo."""
        if scheduler.can_notify_error():
            engine.notifier.notify(f"⚠️ <b>Fallo</b> {prefix}\n{type(exc).__name__}: {exc}")

    logger.info(
        "Daemon iniciado | modo=%s | %d símbolos | ciclo=%ds | informe=%ds | log=%s",
        config.mode.upper(), len(symbols), interval, report_interval, log_file,
    )
    try:
        balance_val = engine.equity()
    except Exception:
        balance_val = None
    engine.notifier.notify(render_welcome_message(config, equity=balance_val))

    _maybe_first_run_api_check(engine, config)
    _maybe_start_sniper(config, engine.notifier)
    _maybe_start_carry(config, engine.notifier, engine=engine)
    _maybe_start_xsmom(config, engine.notifier)
    # Deja un status.json inicial (hilo principal) para que el publicador ya tenga
    # qué subir en su primera vuelta, sin esperar al primer informe.
    try:
        write_status(engine, config)
    except Exception:
        logger.warning("No pude escribir el status inicial")
    _maybe_start_publisher(config, engine)

    # Fija el cortafuegos de pérdida diaria contra el equity REAL de arranque
    # (en live es el balance de la cuenta, no el starting_balance del config).
    try:
        eq0 = engine.equity()
        # Antes de nada: si el ATH persistido pertenece a un capital anterior y ya
        # implicaría un drawdown por encima del límite en reposo, re-anclarlo evita
        # que el disyuntor global salte en el primer ciclo sin haber operado.
        engine.risk.anchor_on_start(eq0)
        engine.storage.set_state("ath_equity", engine.risk.ath_equity)
        engine.risk.reset_day(eq0)
    except Exception:
        logger.warning("No pude fijar el equity inicial para el cortafuegos diario")

    # Evaluación inicial de Fuerza Relativa (RS) y Radar de Funding en el arranque
    radar_cooldowns: dict[str, float] = {}
    try:
        _maybe_evaluate_rs(engine, config, notify=True)
        symbols = _validate_symbols(engine, config.symbols())
    except Exception:
        logger.warning("Fallo en la evaluación inicial de RS")

    try:
        evaluate_funding_radar(config, engine.exchange, engine.notifier, radar_cooldowns)
    except Exception:
        logger.warning("Fallo en el escaneo inicial del radar de funding")

    stopper = _GracefulStop()
    stopper.install()

    try:
        while True:
            try:
                now = datetime.now(timezone.utc)

                # Evaluación de Fuerza Relativa (RS) y Radar de Funding cada 4 Horas (00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC)
                if scheduler.check_4h_slot(now):
                    try:
                        logger.info("Evaluando Fuerza Relativa (RS) en slot 4H: %s %02dh UTC", now.date(), (now.hour // 4) * 4)
                        _maybe_evaluate_rs(engine, config)
                        symbols = _validate_symbols(engine, config.symbols())
                    except Exception:
                        logger.exception("Fallo al evaluar RS en cierre de 4H")
                    try:
                        evaluate_funding_radar(config, engine.exchange, engine.notifier, radar_cooldowns)
                    except Exception:
                        logger.exception("Fallo al evaluar Radar de Funding en cierre de 4H")

                # Nuevo día UTC: reinicia el límite de pérdida diaria y envía el informe oficial.
                if scheduler.is_new_utc_day(now):
                    engine.risk.reset_day(engine.equity())
                    logger.info("Nuevo día UTC (%s): cortafuegos diario reiniciado", scheduler.current_day)
                    try:
                        report_txt = render_daily_report_telegram(engine, config)
                        engine.notifier.notify(f"🌅 <b>INFORME DIARIO DE MEDIANOCHE (00:00 UTC)</b>\n\n{report_txt}")
                    except Exception:
                        logger.exception("Fallo enviando el informe diario de medianoche")

                # Un ciclo sobre todo el universo (símbolos activos + posiciones abiertas pendientes).
                open_symbols = [p.symbol for p in engine.positions]
                loop_symbols = list(dict.fromkeys(symbols + open_symbols))

                for symbol in loop_symbols:
                    try:
                        try:
                            tf = config.instrument(symbol).timeframe
                        except KeyError:
                            tf = "1d"
                        candles = engine.exchange.fetch_ohlcv(
                            symbol, tf, config.lookback
                        )
                        if len(candles) < 2:
                            continue
                        candles_cache[symbol] = candles

                        # Actualizar siempre el precio en vivo y evaluar salidas continuas (SL/TP) en cada sondeo de 60s
                        live_price = float(candles["close"].iloc[-1])
                        engine.last_prices[symbol] = live_price
                        engine._check_exits(symbol, live_price, candles=candles)

                        # Decidir entradas solo sobre velas CERRADAS (descarta la vela en
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
                if scheduler.is_alive_due():
                    _notify_alive(engine, config)

                # Informe periódico a disco + resumen en el log.
                if scheduler.is_report_due():
                    write_report_snapshot(
                        engine.storage, config.risk.quote_currency, report_path,
                        config.risk.starting_balance,
                    )
                    s = engine.storage.summary()
                    logger.info(
                        "Informe actualizado (%s) | ops=%d | P&L=%.2f %s | equity=%.2f | %s",
                        report_path, s["trades"], s["pnl_abs"],
                        config.risk.quote_currency, engine.equity(),
                        "OPERANDO" if not engine.risk.halted else "DETENIDO (límite diario)",
                    )

            except Exception as exc:
                # Cualquier fallo inesperado del bucle: log, avisa y seguimos vivos.
                logger.exception("Error inesperado en el bucle principal; continúo")
                _notify_fail("en el bucle principal", exc)

            # Corrige las operaciones que el exchange no confirmó a tiempo (precio y comisión reales).
            try:
                engine.reconcile_fills()
            except Exception:
                logger.exception("No pude confirmar las ejecuciones pendientes; lo reintento en el próximo ciclo")

            # Status al día en cada ciclo (lo que sube el publicador al gist).
            _refresh_status(engine, config)

            _wait_cycle(engine, interval, exit_poll, candles_cache, sleep=stopper.sleep)

    except KeyboardInterrupt:
        logger.info("%s. Guardando informe final y cerrando.",
                    "Parada solicitada (SIGTERM)" if stopper.requested else "Interrumpido por el usuario")
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
