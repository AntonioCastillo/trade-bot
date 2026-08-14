"""Carga y validación de la configuración (config.yaml + secretos de .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass
class RiskConfig:
    quote_currency: str = "USDT"
    starting_balance: float = 10_000.0
    position_size_pct: float = 0.05
    max_open_positions: int = 5
    stop_loss_pct: float = 0.03
    take_profit_pct: float = 0.06
    max_daily_loss_pct: float = 0.10
    max_account_drawdown_pct: float = 0.15


@dataclass
class EngineConfig:
    poll_interval_seconds: int = 60
    fee_pct: float = 0.001
    slippage_pct: float = 0.0005
    report_interval_seconds: int = 900        # cada cuánto vuelca el informe a disco
    alive_interval_seconds: int = 21600       # señal de vida a Telegram (6 h)
    error_notify_interval_seconds: int = 1800  # anti-spam de avisos de fallo (30 min)


@dataclass
class SniperConfig:
    """Configuración del sniper de recién listadas (experimental, alto riesgo)."""

    enabled: bool = False
    poll_interval_seconds: int = 30
    position_size_pct: float = 0.02      # % del balance por tiro (bajo a propósito)
    take_profit_pct: float = 0.5         # objetivo alto (+50%)
    stop_loss_pct: float = 0.15          # corte si el pump falla (-15%)
    timeout_minutes: int = 60            # si no salta TP/SL, salir por tiempo
    max_concurrent: int = 3
    baseline_path: str = "data/known_symbols.json"


@dataclass
class CarryConfig:
    """Funding-rate carry delta-neutral (long spot + short perp). Subsistema aparte
    (necesita futuros). Se lanza con scripts/carry.py."""

    enabled: bool = False
    symbols: list[str] = field(default_factory=list)   # spot; el perp = symbol + ":USDT"
    notional_pct: float = 0.20        # % del balance por posición (por pata)
    min_annualized_pct: float = 5.0   # abrir solo si el funding anualizado supera esto
    exit_annualized_pct: float = 0.0  # cerrar si cae por debajo (p.ej. funding negativo)
    poll_interval_seconds: int = 300
    fee_pct: float = 0.0008           # comisión por pata (aprox, taker con descuento)
    # --- Ejecución REAL de futuros (activa sola con mode=live; riesgo de liquidación) ---
    leverage: float = 1.0             # apalancamiento de la pata corta (1x = liquidación lejísimos)
    max_notional_usdt: float = 50.0   # tope DURO de USDT por posición (por pata)
    liquidation_buffer_pct: float = 0.15  # cierre de emergencia si el precio queda a <15% de la liquidación


@dataclass
class XSMomConfig:
    """Momentum transversal: rankea una cesta de majors, mantiene el top-K
    (solo-largos, equal-weight), rebalanceo semanal, a CASH si BTC<SMA200.
    Validado walk-forward: bate al equal-weight OOS; overlay de tendencia doma el
    drawdown. Subsistema aparte (paper), como el carry/sniper."""

    enabled: bool = False
    universe: list[str] = field(default_factory=list)
    lookback_days: int = 30           # ventana de momentum
    top_k: int = 3                    # nº de activos que se mantienen
    rebalance_days: int = 7           # cada cuánto rebalancea (semanal)
    trend_filter: bool = True         # a cash cuando el líder está bajo su SMA
    trend_symbol: str = "BTC/USDT"
    trend_sma: int = 200
    fee_pct: float = 0.001            # comisión real por lado (0.1%)
    leverage: float = 1.0             # apalancamiento en futuros
    poll_interval_seconds: int = 3600  # cada cuánto comprueba si toca rebalancear


@dataclass
class HedgingConfig:
    """Configuración de la cobertura dinámica (hedging)."""

    enabled: bool = False
    symbol: str = "BTC/USDT"
    ratio: float = 0.5
    min_positions: int = 2



@dataclass
class Instrument:
    """Un símbolo concreto ya resuelto con su estrategia y su riesgo efectivo."""

    symbol: str
    category: str
    strategy_name: str
    strategy_params: dict[str, Any]
    stop_loss_pct: float
    take_profit_pct: float
    position_size_pct: float
    trailing_stop_pct: float = 0.0
    max_concurrent_per_symbol: int = 1   # >1 para grid (varios peldaños a la vez)
    regimes: list[str] = field(default_factory=list)  # regímenes en los que opera; vacío = siempre
    regime_volatile_atr_pct: float | None = None  # umbral ATR% para "volatile" (None=default 2%)
    timeframe: str = "1h"                # marco de vela de ESTA cabeza


@dataclass
class Credentials:
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""
    telegram_token: str = ""
    telegram_chat_id: str = ""

    @property
    def is_complete(self) -> bool:
        return bool(self.api_key and self.api_secret and self.api_passphrase)

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)


@dataclass
class Config:
    mode: str = "paper"
    exchange: str = "kucoin"
    timeframe: str = "1h"
    lookback: int = 300
    instruments: list[Instrument] = field(default_factory=list)
    risk: RiskConfig = field(default_factory=RiskConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)
    sniper: SniperConfig = field(default_factory=SniperConfig)
    carry: CarryConfig = field(default_factory=CarryConfig)
    xsmom: XSMomConfig = field(default_factory=XSMomConfig)
    hedging: HedgingConfig = field(default_factory=HedgingConfig)
    db_path: str = "data/tradebot.db"
    log_level: str = "INFO"
    credentials: Credentials = field(default_factory=Credentials)

    def validate(self) -> None:
        if self.mode not in ("paper", "live"):
            raise ValueError(f"mode inválido: {self.mode!r} (usa 'paper' o 'live')")
        if self.mode == "live" and not self.credentials.is_complete:
            raise ValueError(
                "mode=live requiere KUCOIN_API_KEY, KUCOIN_API_SECRET y "
                "KUCOIN_API_PASSPHRASE en el .env"
            )
        if not self.instruments and not (
            self.sniper.enabled or self.carry.enabled or self.xsmom.enabled
        ):
            raise ValueError("Nada que ejecutar: sin instrumentos ni subsistemas activos")
        for ins in self.instruments:
            if not 0 < ins.position_size_pct <= 1:
                raise ValueError(
                    f"position_size_pct de {ins.symbol} debe estar en (0, 1]"
                )
            if ins.stop_loss_pct <= 0 or ins.take_profit_pct <= 0:
                raise ValueError(f"SL/TP de {ins.symbol} deben ser > 0")

    def symbols(self) -> list[str]:
        return [ins.symbol for ins in self.instruments]

    def instrument(self, symbol: str) -> Instrument:
        for ins in self.instruments:
            if ins.symbol == symbol:
                return ins
        raise KeyError(symbol)

    def effective_db_path(self) -> str:
        """BD separada por modo: paper y live NUNCA mezclan histórico.
        data/tradebot.db -> data/tradebot_paper.db o data/tradebot_live.db."""
        if self.db_path == ":memory:":
            return self.db_path
        p = Path(self.db_path)
        return str(p.with_name(f"{p.stem}_{self.mode}{p.suffix}"))


def _build_instruments(
    universe: list[dict], risk: RiskConfig, default_timeframe: str
) -> list[Instrument]:
    """Aplana el universo por categorías en una lista de instrumentos, aplicando
    los overrides de riesgo de cada categoría sobre los valores globales."""
    instruments: list[Instrument] = []
    seen: set[str] = set()
    for cat in universe or []:
        name = cat.get("name", "sin_categoria")
        strategy_name = cat.get("strategy", "mean_reversion")
        params = cat.get("params") or {}
        overrides = cat.get("risk") or {}
        for symbol in cat.get("symbols") or []:
            if symbol in seen:
                raise ValueError(f"Símbolo duplicado en el universo: {symbol}")
            seen.add(symbol)
            instruments.append(
                Instrument(
                    symbol=symbol,
                    category=name,
                    strategy_name=strategy_name,
                    strategy_params=dict(params),
                    stop_loss_pct=overrides.get("stop_loss_pct", risk.stop_loss_pct),
                    take_profit_pct=overrides.get(
                        "take_profit_pct", risk.take_profit_pct
                    ),
                    position_size_pct=overrides.get(
                        "position_size_pct", risk.position_size_pct
                    ),
                    trailing_stop_pct=overrides.get("trailing_stop_pct", 0.0),
                    max_concurrent_per_symbol=cat.get("max_concurrent_per_symbol", 1),
                    regimes=list(cat.get("regimes") or []),
                    regime_volatile_atr_pct=cat.get("regime_volatile_atr_pct"),
                    timeframe=cat.get("timeframe") or default_timeframe,
                )
            )
    return instruments


def load_config(path: str | Path = "config.yaml") -> Config:
    """Lee config.yaml, mezcla los secretos del .env y valida el resultado."""
    load_dotenv()

    raw: dict[str, Any] = {}
    cfg_path = Path(path)
    if cfg_path.exists():
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    risk = RiskConfig(**(raw.get("risk") or {}))
    engine = EngineConfig(**(raw.get("engine") or {}))
    sniper = SniperConfig(**(raw.get("sniper") or {}))
    carry = CarryConfig(**(raw.get("carry") or {}))
    xsmom = XSMomConfig(**(raw.get("xsmom") or {}))
    hedging = HedgingConfig(**(raw.get("hedging") or {}))
    global_timeframe = raw.get("timeframe", "1h")
    instruments = _build_instruments(raw.get("universe") or [], risk, global_timeframe)

    credentials = Credentials(
        api_key=os.getenv("KUCOIN_API_KEY", ""),
        api_secret=os.getenv("KUCOIN_API_SECRET", ""),
        api_passphrase=os.getenv("KUCOIN_API_PASSPHRASE", ""),
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
    )

    cfg = Config(
        mode=raw.get("mode", "paper"),
        exchange=raw.get("exchange", "kucoin"),
        timeframe=raw.get("timeframe", "1h"),
        lookback=int(raw.get("lookback", 300)),
        instruments=instruments,
        risk=risk,
        engine=engine,
        sniper=sniper,
        carry=carry,
        xsmom=xsmom,
        hedging=hedging,
        db_path=(raw.get("storage") or {}).get("db_path", "data/tradebot.db"),
        log_level=(raw.get("logging") or {}).get("level", "INFO"),
        credentials=credentials,
    )
    cfg.validate()
    return cfg
