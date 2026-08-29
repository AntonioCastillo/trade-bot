"""Gestión de riesgo. Traduce señales en órdenes dimensionadas y decide salidas.

Es la última línea de defensa: puede vetar cualquier señal. Cada instrumento
aporta su propio tamaño de posición y sus SL/TP (por categoría); los límites de
cartera (máximo de posiciones, pérdida diaria) son globales.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import Instrument, RiskConfig
from .models import Order, Position, Side, Signal, SignalType

logger = logging.getLogger(__name__)


@dataclass
class RiskDecision:
    order: Order | None
    reason: str


class RiskManager:
    def __init__(self, config: RiskConfig):
        self.config = config
        self._day_start_equity: float | None = None
        self._halted = False
        self._halted_reason = ""
        self.ath_equity = 0.0
        self.global_drawdown = 0.0

    def set_ath_equity(self, value: float) -> None:
        self.ath_equity = max(self.ath_equity, value)

    # --- Control de pérdida diaria y global ---------------------------------------

    def register_equity(self, equity: float) -> None:
        # 1. Pérdida diaria
        if self._day_start_equity is None:
            self._day_start_equity = equity
        else:
            daily_dd = (self._day_start_equity - equity) / self._day_start_equity
            if daily_dd >= self.config.max_daily_loss_pct and not self._halted:
                self._halted = True
                self._halted_reason = "drawdown_diario"
                logger.error(
                    "LIMITE DE PERDIDA DIARIA alcanzado (%.2f%%). Bot detenido.",
                    daily_dd * 100,
                )

        # 2. Pérdida global de la cuenta (desde ATH)
        if self.ath_equity <= 0.0:
            self.ath_equity = equity
        else:
            self.ath_equity = max(self.ath_equity, equity)

        self.global_drawdown = (self.ath_equity - equity) / self.ath_equity
        max_global = getattr(self.config, "max_account_drawdown_pct", 0.15)
        if max_global > 0 and self.global_drawdown >= max_global and not self._halted:
            self._halted = True
            self._halted_reason = "drawdown_cuenta"
            logger.critical(
                "DISYUNTOR CRITICO: LIMITE DE PERDIDA GLOBAL DE CUENTA alcanzado (%.2f%%). Bot detenido.",
                self.global_drawdown * 100,
            )

    def reset_day(self, equity: float) -> None:
        self._day_start_equity = equity
        # Solo reseteamos el halt si no fue causado por el disyuntor global de cuenta
        if self._halted_reason != "drawdown_cuenta":
            self._halted = False
            self._halted_reason = ""

    def anchor_on_start(self, equity: float) -> None:
        """Al arrancar el servicio, evita que un `ath_equity` persistido de un
        régimen de capital ANTERIOR (tras bajar el starting_balance, retirar
        fondos o resetear el paper) dispare el disyuntor global sin que se haya
        operado nada — SIN desarmar el disyuntor ante una pérdida real.

        Reglas:
          - Drawdown importado < límite: pico legítimo, se conserva (anti-gaming).
          - Drawdown importado ≥ límite y equity EN/POR ENCIMA de la base de
            capital (starting_balance): no se ha perdido principal, el pico es de
            otro capital -> re-ancla al equity actual y limpia el halt.
          - Drawdown importado ≥ límite pero equity POR DEBAJO de la base: es
            pérdida real -> NO desarmar; ancla el máximo a la base para que el
            disyuntor mida el drawdown real desde el capital de arranque."""
        if equity <= 0:
            return
        max_global = getattr(self.config, "max_account_drawdown_pct", 0.15)
        if self.ath_equity <= 0 or max_global <= 0:
            self.ath_equity = max(self.ath_equity, equity)
            return

        imported_dd = (self.ath_equity - equity) / self.ath_equity
        if imported_dd < max_global:
            # Pico dentro de tolerancia: legítimo, se conserva.
            self.ath_equity = max(self.ath_equity, equity)
            return

        # El pico guardado ya cortaría en reposo. Discriminador de capital real:
        baseline = float(getattr(self.config, "starting_balance", 0.0) or 0.0)
        if baseline > 0 and equity < baseline * (1 - 1e-6):
            # Pérdida real por debajo del capital de arranque: NO desarmar. Ancla
            # el máximo a la base para medir el drawdown real desde ahí (si ya lo
            # cruza, saltará en el primer register_equity).
            logger.warning(
                "Equity de arranque (%.2f) por DEBAJO de la base de capital "
                "(%.2f): es pérdida real, mantengo el disyuntor armado desde la "
                "base (ignoro el pico persistido %.2f).",
                equity, baseline, self.ath_equity,
            )
            self.ath_equity = baseline
            self.global_drawdown = (baseline - equity) / baseline
            return

        logger.warning(
            "ATH persistido (%.2f) implica un drawdown del %.1f%% ya al arrancar "
            "(equity %.2f, base %.2f) y el equity NO está por debajo de la base: "
            "pico de un capital anterior, re-anclo el máximo al equity actual.",
            self.ath_equity, imported_dd * 100, equity, baseline,
        )
        self.ath_equity = equity
        self.global_drawdown = 0.0
        if self._halted_reason == "drawdown_cuenta":
            self._halted = False
            self._halted_reason = ""

    @property
    def halted(self) -> bool:
        return self._halted

    @property
    def halted_reason(self) -> str:
        return self._halted_reason

    # --- Entradas ------------------------------------------------------------------

    def evaluate_entry(
        self,
        signal: Signal,
        instrument: Instrument,
        balance: float,
        open_positions: list[Position],
        current_atr: float = 0.0,
    ) -> RiskDecision:
        if self._halted:
            return RiskDecision(None, f"bot detenido por gestión de riesgo ({self._halted_reason})")
        if signal.type is SignalType.HOLD:
            return RiskDecision(None, "señal HOLD")
        if len(open_positions) >= self.config.max_open_positions:
            return RiskDecision(None, "máximo de posiciones abiertas alcanzado")
        same_symbol = sum(1 for p in open_positions if p.symbol == signal.symbol)
        if same_symbol >= instrument.max_concurrent_per_symbol:
            return RiskDecision(
                None, f"ya hay {same_symbol} posición(es) en {signal.symbol}"
            )

        # Filtro de exposición total: reservar un % de la cuenta en USDT líquido.
        if self.config.max_total_exposure_pct < 1.0 and balance > 0:
            current_exposure = sum(
                p.entry_price * p.amount for p in open_positions
            )
            new_notional = balance * instrument.position_size_pct
            if (current_exposure + new_notional) / balance > self.config.max_total_exposure_pct:
                return RiskDecision(
                    None,
                    f"exposición total superaría {self.config.max_total_exposure_pct:.0%} "
                    f"({current_exposure + new_notional:.2f} / {balance:.2f})"
                )

        capital = balance * instrument.position_size_pct

        # Position sizing adaptativo por volatilidad (ATR)
        if instrument.volatility_sizing and current_atr > 0 and signal.price > 0:
            atr_pct = current_atr / signal.price
            if atr_pct > 0:
                vol_factor = instrument.volatility_ref_atr_pct / atr_pct
                vol_factor = max(instrument.volatility_size_min,
                                min(instrument.volatility_size_max, vol_factor))
                capital *= vol_factor
                logger.debug(
                    "Volatility sizing: ATR%%=%.2f%%, ref=%.2f%%, factor=%.2fx, capital=%.2f",
                    atr_pct * 100, instrument.volatility_ref_atr_pct * 100,
                    vol_factor, capital,
                )
        if capital <= 0 or signal.price <= 0:
            return RiskDecision(None, "capital o precio no válidos")

        amount = capital / signal.price
        side = Side.BUY if signal.type is SignalType.BUY else Side.SELL
        order = Order(
            symbol=signal.symbol,
            side=side,
            amount=amount,
            price=signal.price,
            reason=signal.reason,
        )
        return RiskDecision(order, f"entrada aprobada: {side.value} {amount:.8f}")

    def build_position(
        self,
        instrument: Instrument,
        side: Side,
        amount: float,
        entry_price: float,
        entry_fee: float,
        reason: str,
    ) -> Position:
        sl, tp = instrument.stop_loss_pct, instrument.take_profit_pct
        if side is Side.BUY:
            stop = entry_price * (1 - sl)
            take = entry_price * (1 + tp)
        else:
            stop = entry_price * (1 + sl)
            take = entry_price * (1 - tp)
        return Position(
            symbol=instrument.symbol,
            side=side,
            amount=amount,
            entry_price=entry_price,
            stop_loss=stop,
            take_profit=take,
            category=instrument.category,
            strategy_name=instrument.strategy_name,
            entry_fee=entry_fee,
            reason=reason,
            trailing_stop_pct=instrument.trailing_stop_pct,
            peak_price=entry_price,
            partial_tp_pct=getattr(instrument, "partial_take_profit_pct", 0.0),
            partial_tp_ratio=getattr(instrument, "partial_take_profit_ratio", 0.5),
            partial_tp_done=False,
            use_atr_trailing=getattr(instrument, "use_atr_trailing", False),
            atr_trailing_mult=getattr(instrument, "atr_trailing_mult", 3.0),
        )

    # --- Salidas -------------------------------------------------------------------

    def evaluate_exit(self, position: Position, current_price: float, current_atr: float = 0.0) -> RiskDecision:
        close_side = Side.SELL if position.side is Side.BUY else Side.BUY

        self._update_trailing_stop(position, current_price, current_atr=current_atr)

        # 1) Comprobar Toma Parcial de Beneficios (Partial TP)
        if not position.partial_tp_done and position.partial_tp_pct > 0:
            if position.side is Side.BUY:
                hit_partial = current_price >= position.entry_price * (1 + position.partial_tp_pct)
            else:
                hit_partial = current_price <= position.entry_price * (1 - position.partial_tp_pct)
            if hit_partial:
                partial_amount = position.amount * position.partial_tp_ratio
                order = Order(
                    symbol=position.symbol,
                    side=close_side,
                    amount=partial_amount,
                    price=current_price,
                    reason="partial-take-profit",
                )
                return RiskDecision(order, "toma parcial de beneficios")

        if position.side is Side.BUY:
            hit_stop = current_price <= position.stop_loss
            hit_take = current_price >= position.take_profit
        else:
            hit_stop = current_price >= position.stop_loss
            hit_take = current_price <= position.take_profit

        if hit_stop or hit_take:
            if hit_stop:
                reason = "trailing-stop" if (position.trailing_stop_pct > 0 or position.use_atr_trailing) else "stop-loss"
            else:
                reason = "take-profit"
            order = Order(
                symbol=position.symbol,
                side=close_side,
                amount=position.amount,
                price=current_price,
                reason=reason,
            )
            return RiskDecision(order, f"cierre por {reason}")

        return RiskDecision(None, "posición dentro de rango")

    def _update_trailing_stop(self, position: Position, current_price: float, current_atr: float = 0.0) -> None:
        """Arrastra el stop siguiendo al mejor precio alcanzado. Solo lo mueve a
        favor: nunca afloja el stop una vez apretado."""
        if position.use_atr_trailing and current_atr > 0:
            dist = current_atr * position.atr_trailing_mult
            if position.side is Side.BUY:
                position.peak_price = max(position.peak_price, current_price)
                trail = position.peak_price - dist
                position.stop_loss = max(position.stop_loss, trail)
            else:
                position.peak_price = min(position.peak_price, current_price)
                trail = position.peak_price + dist
                position.stop_loss = min(position.stop_loss, trail)
            return

        if position.trailing_stop_pct <= 0:
            return
        pct = position.trailing_stop_pct
        if position.side is Side.BUY:
            position.peak_price = max(position.peak_price, current_price)
            trail = position.peak_price * (1 - pct)
            position.stop_loss = max(position.stop_loss, trail)
        else:
            position.peak_price = min(position.peak_price, current_price)
            trail = position.peak_price * (1 + pct)
            position.stop_loss = min(position.stop_loss, trail)
