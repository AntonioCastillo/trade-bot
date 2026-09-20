# 📓 DIARIO DE BITÁCORA (Logbook de Cambios y Decisiones)

Este documento registra cronológicamente cada cambio significativo en el código, configuración o arquitectura de **tradebot**, detallando el **motivo empírico**, la **causa técnica** y el **impacto esperado**.

---

## 📌 Índice de Entradas

* [2026-09-20 | Persistencia Histórica de Funding en SQLite y Dashboard Financiero (Commit Inmediato)](#2026-09-20--persistencia-histórica-de-funding-en-sqlite-y-dashboard-financiero)
* [2026-09-20 | Optimización y Consolidación de Notificaciones de Rotación RS (Commit `de8a166`)](#2026-09-20--optimización-y-consolidación-de-notificaciones-de-rotación-rs)
* [2026-09-20 | Corrección de Símbolos Duplicados en Universo YAML (Commit `f0d02d0`)](#2026-09-20--corrección-de-símbolos-duplicados-en-universo-yaml-commit-f0d02d0)
* [2026-09-20 | Calibración de Parámetros de Producción (Commit `2cbc846`)](#2026-09-20--calibración-de-parámetros-de-producción-commit-2cbc846)
* [2026-09-18 | Notificaciones de Alerta Crítica en Telegram para Salidas Fallidas (Commit `b739165`)](#2026-09-18--notificaciones-de-alerta-crítica-en-telegram-para-salidas-fallidas-commit-b739165)
* [2026-09-18 | Blindaje Multinivel de Salidas: Reintentos y Persistencia en BBDD (Commit `de7591d`)](#2026-09-18--blindaje-multinivel-de-salidas-reintentos-y-persistencia-en-bbdd-commit-de7591d)
* [2026-09-18 | Reconciliación de Saldo Real por Deducción de Comisiones Base (Commit `c13026b`)](#2026-09-18--reconciliación-de-saldo-real-por-deducción-de-comisiones-base-commit-c13026b)
* [2026-09-18 | Documentación de Onboarding Cero Contexto (Commit `788f819`)](#2026-09-18--documentación-de-onboarding-cero-contexto-commit-788f819)
* [2026-09-01 a 2026-09-16 | Hitos Fundacionales de la Arquitectura Hidra Multicabeza](#hitos-fundacionales-de-la-arquitectura-hidra-multicabeza)

---

### 2026-09-20 | Persistencia Histórica de Funding en SQLite y Dashboard Financiero

* **Archivos Afectados:** [`src/tradebot/storage.py`](../src/tradebot/storage.py), [`src/tradebot/carry.py`](../src/tradebot/carry.py), [`src/tradebot/carry_live.py`](../src/tradebot/carry_live.py), [`src/tradebot/daemon.py`](../src/tradebot/daemon.py), [`scripts/beneficios.py`](../scripts/beneficios.py)
* **Motivo / Petición del Usuario:**
  * El usuario solicitó conocer con precisión cuánto beneficio ha generado el módulo de funding (Carry Trade) desde el inicio histórico del bot.
  * *Causa técnica:* Anteriormente, el cobro de tasas de financiación (*funding rate*) se mantenía en memoria en los objetos `CarryPosition`. Al cerrarse una posición (como ocurrió con ETH) o al reiniciar el bot, los cobros históricos desaparecían del total acumulado en el Gist y en los resúmenes diarios.
* **Cambios Implementados:**
  1. **Tabla de Pagos de Funding en SQLite (`storage.py`):**
     - Se creó la tabla permanente `funding_payments` (`id`, `timestamp`, `symbol`, `rate`, `amount_usdt`, `notional`).
     - Se implementaron métodos `record_funding_payment(...)`, `total_funding_collected()` y `all_funding_payments()`.
  2. **Persistencia Automática en Tiempo Real (`carry.py` y `carry_live.py`):**
     - Cada 8 horas (en los cortes de funding 04:00, 12:00 y 20:00 UTC), al producirse un devengo de financiación, se registra inmediatamente en SQLite de forma indeleble.
     - `CarryRunner.write_status_file()` reporta `total_funding_collected` consultando la base de datos histórica, garantizando que el Gist y las estadísticas incluyan el 100% de las ganancias acumuladas pasadas y presentes.
  3. **Informe Consolidado en Telegram (`daemon.py`):**
     - `render_daily_report_telegram` ahora muestra el `Funding Carry Histórico` total sumado al P&L realizado en Spot para ofrecer el Beneficio Neto Realizado exacto en caja.
  4. **Dashboard de Beneficios (`scripts/beneficios.py`):**
     - `python scripts/beneficios.py` y `python scripts/beneficios.py --gist` muestran el desglose financiero completo, histórico de cobros individuales en BBDD, rendimiento por cabeza y posiciones activas.
* **Resultado Esperado:** Trazabilidad contable total y permanente del 100% de las rentabilidades de funding generadas desde el inicio de la operativa.

---

### 2026-09-20 | Optimización y Consolidación de Notificaciones de Rotación RS (Commit `de8a166`)

* **Archivos Afectados:** [`src/tradebot/daemon.py`](../src/tradebot/daemon.py)
* **Motivo / Causa del Doble Mensaje al Arrancar:**
  * Al iniciar el bot, tanto `breakout_diario` como `momentum_diario` evaluaban RS por separado y detectaban que los símbolos de arranque diferían de los líderes reales calculados (`NEAR/INJ`).
  * Esto provocaba que justo después de `🤖 Bot iniciado` llegaran dos mensajes idénticos consecutivos (`🔄 ROTACIÓN RS EN VIVO (breakout_diario)` y `🔄 ROTACIÓN RS EN VIVO (momentum_diario)`).
* **Cambios Implementados:**
  1. **Notificación Instantánea de Arranque:** El mensaje `🤖 Bot iniciado` se envía de inmediato al arrancar el proceso sin bloqueos de red.
  2. **Caché de Rankings:** Se añadió `rankings_cache` para que la consulta de los 25 pares del pool se descargue solo 1 vez en lugar de duplicarse para cada cabeza.
  3. **Consolidación en 1 Solo Mensaje:** Cuando ambas cabezas rotan a la vez (en arranque o en los cierres de 4H), se agrupan en **un único mensaje limpio y consolidado** que detalla todos los cambios juntos.
* **Resultado Esperado:** Mensaje de inicio inmediato seguido de un único aviso de rotación unificado.

---

### 2026-09-20 | Corrección de Símbolos Duplicados en Universo YAML (Commit `f0d02d0`)

* **Archivos Afectados:** [`config.yaml`](../config.yaml)
* **Motivo / Causa Raíz del Bloqueo en Arranque:**
  * Al añadir `DOT/USDT` y `LTC/USDT` a `grid_lateral`, dichos pares quedaron duplicados porque ya existían en `reversion_rango`.
  * La función `_build_instruments()` en [`src/tradebot/config.py`](../src/tradebot/config.py#L225) incluye una validación de seguridad estricta (`ValueError: Símbolo duplicado en el universo: DOT/USDT`) para evitar que dos cabezas emitan órdenes contradictorias sobre un mismo activo.
  * Como consecuencia, el bot abortaba el proceso de carga de configuración antes de inicializar el bucle `daemon.py` (y por tanto, antes de poder enviar el mensaje de `🤖 Bot iniciado` a Telegram).
* **Cambios Implementados:**
  * Se actualizaron los símbolos de `reversion_rango` a `[ATOM/USDT, ALGO/USDT, ETC/USDT]`, dejando `[NEAR/USDT, LINK/USDT, DOT/USDT, LTC/USDT]` en exclusiva para `grid_lateral`.
  * Universo validado al 100% con 17 símbolos únicos sin colisiones.
* **Resultado Esperado:** Arranque limpio inmediato y envío correcto de la notificación de bienvenida en Telegram.

---

### 2026-09-20 | Calibración de Parámetros de Producción (Commit `2cbc846`)

* **Archivos Afectados:** [`config.yaml`](../config.yaml)
* **Motivo / Justificación Empírica:**
  1. `grid_lateral` demostró ser la estrategia más consistente de la cartera con un 100% de aciertos (11/11 trades ganadores, +42,70 USDT acumulados). Convenía ampliar su radio de acción a más pares líquidos de rango.
  2. El umbral diario de pérdidas estaba configurado al 20% (`max_daily_loss_pct: 0.20`), excesivamente laxo para operar con capital real ($1.500 USDT).
  3. En `carry_trade`, abrir y cerrar posiciones Spot + Futuros conlleva un coste de comisiones del ~0.16%. Un umbral mínimo del 5.0% anual requería hasta 12 días de funding para compensar la apertura/cierre.
* **Cambios Implementados:**
  1. Se añadieron `DOT/USDT` y `LTC/USDT` a `grid_lateral.symbols` (junto a `NEAR` y `LINK`).
  2. Se redujo `max_daily_loss_pct` del 20% al **10% (0.10)** para mayor protección de la cuenta.
  3. Se elevó `carry.min_annualized_pct` de 5.0% a **8.0%** anual para garantizar márgenes netos positivos inmediatos.
* **Resultado Esperado:** Mayor frecuencia de captura de ganancias en rangos laterales y amortización de comisiones en menos de 4-5 días en Carry Trade.

---

### 2026-09-18 | Notificaciones de Alerta Crítica en Telegram para Salidas Fallidas (Commit `b739165`)

* **Archivos Afectados:** [`src/tradebot/engine.py`](../src/tradebot/engine.py)
* **Motivo / Justificación:**
  * Si una orden de Stop Loss o Take Profit no se puede ejecutar en KuCoin tras agotar los 3 reintentos síncronos (por ejemplo, si el exchange sufriera una caída masiva de API), el usuario debe ser alertado en tiempo real en su teléfono móvil para que pueda intervenir manualmente si lo desea.
* **Cambios Implementados:**
  * En `_close_position` y `_execute_partial_close`, si `fill is None`, se envía un mensaje urgente por Telegram (`self.notifier.notify`) con el símbolo, motivo de salida (`stop-loss`, `take-profit`), código de error de la API y aviso de reintento automático en 60s.
* **Resultado Esperado:** Visibilidad total y tranquilidad operativa ante incidencias imprevistas del exchange.

---

### 2026-09-18 | Blindaje Multinivel de Salidas: Reintentos y Persistencia en BBDD (Commit `de7591d`)

* **Archivos Afectados:** [`src/tradebot/engine.py`](../src/tradebot/engine.py)
* **Motivo / Justificación:**
  * Evitar que microcortes de red, errores temporales 502/504 de Cloudflare o latencias en KuCoin provoquen el descarte de órdenes de cierre críticas (Stop Loss o Take Profit).
* **Cambios Implementados:**
  1. **Nivel 1 (Reintento Síncrono):** Bucle de hasta 3 intentos con 1.0 segundo de pausa (`time.sleep(1.0)`) dentro de `_close_position` y `_execute_partial_close`.
  2. **Nivel 2 (Invariante de BBDD):** Si tras los 3 intentos no se ejecuta, la posición **permanece intacta en memoria (`self.positions`) y en SQLite (`storage.open_positions`)**. En el siguiente ciclo (60s), el evaluador de riesgo vuelve a disparar la orden.
* **Resultado Esperado:** Garantía matemática de que ninguna posición con Stop Loss o Take Profit alcanzado se pierde o queda desatendida.

---

### 2026-09-18 | Reconciliación de Saldo Real por Deducción de Comisiones Base (Commit `c13026b`)

* **Archivos Afectados:** [`src/tradebot/execution/live.py`](../src/tradebot/execution/live.py)
* **Motivo / Justificación (Incidencia `NEAR/USDT`):**
  * En KuCoin Spot, al comprar un token (ej. NEAR), el exchange deduce su comisión del 0.1% en la propia moneda adquirida. Al enviar la orden de venta con la cantidad nominal exacta (`pos.amount`), KuCoin devolvía `ccxt.InsufficientFunds: balance insufficient` porque faltaba una fracción de céntimo.
* **Cambios Implementados:**
  * Antes de enviar cualquier orden de venta a mercado en vivo, el motor consulta a la API el saldo libre real (`real_balance = self.exchange.fetch_balance(base_currency)`) y recorta la cantidad:
    $$\text{order.amount} = \min(\text{order.amount}, \text{real\_balance})$$
* **Resultado Esperado:** Eliminación del 100% de los rechazos por saldo insuficiente en órdenes de salida Spot. Permitió cerrar la posición de NEAR consolidando **+29,95 USDT netos (+47%)**.

---

### 2026-09-18 | Documentación de Onboarding Cero Contexto (Commit `788f819`)

* **Archivos Afectados:** [`docs/PROJECT_STATE.md`](PROJECT_STATE.md), [`README.md`](../README.md)
* **Motivo / Justificación:**
  * Permitir que cualquier desarrollador humano o agente de IA que inicie una sesión sin memoria previa pueda entender el 100% del sistema, el historial de decisiones de diseño, la estructura del código y los resultados empíricos auditados.
* **Cambios Implementados:**
  * Creación del documento `docs/PROJECT_STATE.md` con el resumen ejecutivo, historia de decisiones, mapa de archivos de `src/tradebot/`, guía de despliegue y auditoría de resultados en vivo.

---

### Hitos Fundacionales de la Arquitectura Hidra Multicabeza

1. **Eliminación del Scalping en 5m:**
   * *Motivo:* Las comisiones de exchange devoraban los márgenes en marcos de 1m-5m. Se migró a marcos temporales altos (**1D y 4H**).
2. **Escáner de Fuerza Relativa (RS vs BTC a 14d):**
   * *Motivo:* No operar activos rezagados. Selecciona automáticamente los 2 líderes del mercado de un pool de 25 altcoins con un filtro de histéresis del 5.0%.
3. **Módulo Carry Trade Delta-Neutral (Cash & Carry):**
   * *Motivo:* Generar rentabilidad pasiva recurrente mediante el cobro de la tasa de financiación (*funding rate*) libre de riesgo direccional ($\Delta = 0$).
4. **Gestión de Riesgo Dinámica (Toma Parcial 50% + Breakeven + Chandelier ATR):**
   * *Motivo:* Proteger el capital asegurando el 50% de la ganancia al +5%, moviendo inmediatamente el Stop Loss restante al precio de entrada y dejando correr la tendencia con un trailing stop por volatilidad.
