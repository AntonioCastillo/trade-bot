# 📓 DIARIO DE BITÁCORA (Logbook de Cambios y Decisiones)

Este documento registra cronológicamente cada cambio significativo en el código, configuración o arquitectura de **tradebot**, detallando el **motivo empírico**, la **causa técnica** y el **impacto esperado**.

---

* [2026-09-20 | Refactorización Arquitectónica y Simplificación (Fase 1: Daemon, CLI Unificada y Legacy Archive)](#2026-09-20--refactorización-arquitectónica-y-simplificación-fase-1-daemon-cli-unificada-y-legacy-archive)
* [2026-09-20 | Desmontaje de Carry Trade, Liberación de Liquidez y Radar de Funding >25% (Commit `ba39b8a`)](#2026-09-20--desmontaje-de-carry-trade-liberación-de-liquidez-y-radar-de-funding-25)
* [2026-09-20 | Persistencia y Sincronización Histórica de Funding (KuCoin Futures API -> SQLite) (Commit `85ae9b1`)](#2026-09-20--persistencia-y-sincronización-histórica-de-funding-kucoin-futures-api---sqlite)
* [2026-09-20 | Optimización y Consolidación de Notificaciones de Rotación RS (Commit `de8a166`)](#2026-09-20--optimización-y-consolidación-de-notificaciones-de-rotación-rs)
* [2026-09-20 | Corrección de Símbolos Duplicados en Universo YAML (Commit `f0d02d0`)](#2026-09-20--corrección-de-símbolos-duplicados-en-universo-yaml-commit-f0d02d0)
* [2026-09-20 | Calibración de Parámetros de Producción (Commit `2cbc846`)](#2026-09-20--calibración-de-parámetros-de-producción-commit-2cbc846)
* [2026-09-18 | Notificaciones de Alerta Crítica en Telegram para Salidas Fallidas (Commit `b739165`)](#2026-09-18--notificaciones-de-alerta-crítica-en-telegram-para-salidas-fallidas-commit-b739165)
* [2026-09-18 | Blindaje Multinivel de Salidas: Reintentos y Persistencia en BBDD (Commit `de7591d`)](#2026-09-18--blindaje-multinivel-de-salidas-reintentos-y-persistencia-en-bbdd-commit-de7591d)
* [2026-09-18 | Reconciliación de Saldo Real por Deducción de Comisiones Base (Commit `c13026b`)](#2026-09-18--reconciliación-de-saldo-real-por-deducción-de-comisiones-base-commit-c13026b)
* [2026-09-18 | Documentación de Onboarding Cero Contexto (Commit `788f819`)](#2026-09-18--documentación-de-onboarding-cero-contexto-commit-788f819)
* [2026-09-01 a 2026-09-16 | Hitos Fundacionales de la Arquitectura Hidra Multicabeza](#hitos-fundacionales-de-la-arquitectura-hidra-multicabeza)

---

### 2026-09-20 | Refactorización Arquitectónica y Simplificación (Fase 1: Daemon, CLI Unificada y Legacy Archive)

* **Archivos Afectados:** [`src/tradebot/daemon.py`](../src/tradebot/daemon.py), [`src/tradebot/telegram_views.py`](../src/tradebot/telegram_views.py), [`src/tradebot/scheduler.py`](../src/tradebot/scheduler.py), [`scripts/manage.py`](../scripts/manage.py), [`src/tradebot/strategy/legacy/`](../src/tradebot/strategy/legacy/), [`src/tradebot/strategy/__init__.py`](../src/tradebot/strategy/__init__.py), [`tests/test_scheduler.py`](../tests/test_scheduler.py), [`tests/test_telegram_views.py`](../tests/test_telegram_views.py)
* **Motivo / Petición del Usuario:**
  * El usuario solicitó simplificar y estructurar la arquitectura del bot (sin alterar lógica de negocio): *"analiza la estructura del codigo y del flujo para ver que mejoras podrias aplicar en pos de la claridad y simplicidad del proyecto"*, e indicó: *"empieza con los 3 primeros"*.
* **Cambios Implementados:**
  1. **Desacoplamiento de `daemon.py`:**
     - Extracción de formateo HTML y plantillas de Telegram a [`src/tradebot/telegram_views.py`](../src/tradebot/telegram_views.py) (`render_daily_report_telegram`, `render_welcome_message`, `render_heads_summary`, `render_rs_rotations`).
     - Creación de [`src/tradebot/scheduler.py`](../src/tradebot/scheduler.py) con `EventScheduler` para gestionar limpiamente cortes horarios (00:00 UTC, slots 4H, rate-limit de errores, intervalos de reporte y heartbeat).
  2. **CLI Unificada `scripts/manage.py`:**
     - Centralización de comandos operativos en un CLI único con subcomandos:
       - `python scripts/manage.py status [--gist]`
       - `python scripts/manage.py sync-funding`
       - `python scripts/manage.py close-carry [--dry-run]`
       - `python scripts/manage.py report [db_path]`
       - `python scripts/manage.py verify-api [--usd USD] [--symbol SYMBOL]`
       - `python scripts/manage.py backtest [--limit N] [--config PATH]`
     - Mantiene 100% de compatibilidad regresiva con los scripts individuales existentes.
  3. **Archivado de Estrategias Deprecadas (`src/tradebot/strategy/legacy/`):**
     - Traslado de estrategias de scalping 1m/5m retiradas (`scalping.py`, `rsi_scalper.py`, `mean_reversion.py`) al submódulo `strategy.legacy`.
     - Registro y re-exportación transparente en `src/tradebot/strategy/__init__.py` para preservar compatibilidad de backtests y tests existentes.
* **Verificación:** 207 tests unitarios y de integración ejecutados y pasando al 100% (`207 passed`).

---

### 2026-09-20 | Desmontaje de Carry Trade, Liberación de Liquidez y Radar de Funding >25%

* **Archivos Afectados:** [`config.yaml`](../config.yaml), [`config_futures.yaml`](../config_futures.yaml), [`src/tradebot/config.py`](../src/tradebot/config.py), [`src/tradebot/funding_radar.py`](../src/tradebot/funding_radar.py), [`src/tradebot/daemon.py`](../src/tradebot/daemon.py), [`scripts/close_carry.py`](../scripts/close_carry.py)
* **Motivo / Justificación Económica:**
  * El usuario auditó el coste de oportunidad del Carry Trade: en 20 días solo generó +0.40 USDT con ~$240 USDT inmovilizados (~3.1% APR), mientras que las estrategias Spot (`grid_lateral`, `reversion_rango`) generaron más de +$55 USDT con 100% de aciertos (~260% APR).
  * Se acordó desmontar las posiciones activas de futuros, liberar el 100% del capital para Spot y mantener un radar pasivo que alerte por Telegram solo ante anomalías extremas de funding (>25% anual).
* **Cambios Implementados:**
  1. **Desmontaje Seguro y Cierre en Vivo (`scripts/close_carry.py`):**
     - Venta a mercado de 1.145 SOL en Spot por **+$124.05 USDT**.
     - Recompra a mercado del corto de 11 contratos de SOL en Futuros, liberando **+$114.01 USDT** de colateral.
     - **Liquidez total recuperada:** **+$238.06 USDT** netos de vuelta a la cuenta (saldo libre spot ascendió a 1.117,52 USDT).
  2. **Desactivación de Operativa Automática de Carry:**
     - `carry.enabled: false` en `config.yaml` y `config_futures.yaml`.
  3. **Activación del Radar de Tasas Extremas (`funding_radar.py`):**
     - Escanea los 15 principales contratos perpetuos en el arranque y en cada cierre de 4H.
     - Emite alertas por Telegram si algún activo supera el **25.0% anual** ($> 0.0228\%$ por 8h), con un cooldown de 8 horas por símbolo para evitar duplicidad de mensajes.
* **Resultado Esperado:** 0% exposición a derivados, 100% de capital maximizando el ROI en Spot, y vigilancia pasiva continua de oportunidades de financiación extraordinarias.

---

### 2026-09-20 | Persistencia y Sincronización Histórica de Funding (KuCoin Futures API -> SQLite) (Commit `85ae9b1`)

* **Archivos Afectados:** [`src/tradebot/storage.py`](../src/tradebot/storage.py), [`src/tradebot/execution/futures.py`](../src/tradebot/execution/futures.py), [`src/tradebot/carry_live.py`](../src/tradebot/carry_live.py), [`scripts/sync_funding.py`](../scripts/sync_funding.py), [`scripts/beneficios.py`](../scripts/beneficios.py)
* **Motivo / Petición del Usuario:**
  * El usuario señaló: *"pero no sabremos el historico, solo el acumulado desde ahora"*.
  * *Objetivo:* Recuperar el 100% de los cobros de funding devengados en KuCoin Futuros desde el día 1 en que arrancó el bot (2026-08-31) y sincronizarlos permanentemente en SQLite.
* **Cambios Implementados:**
  1. **Auditoría y Sincronizador de API KuCoin Futuros (`FuturesBroker.fetch_historical_funding_records`):**
     - Consulta la API privada (`futuresPrivateGetFundingHistory`) con paginación de todos los pares operados (`ETH`, `SOL`, etc.).
     - Recupera el identificador único `id`, `timePoint`, tasa 8h, nocional y el importe real devengado en USDT.
     - **Hallazgo verificado:** Se recuperaron **61 cobros históricos** de funding por un total de **+0.402374 USDT** (ETH: +0.3168 USDT en 50 cobros, SOL: +0.0856 USDT en 11 cobros).
  2. **Persistencia Idempotente con `payment_id` (`storage.py`):**
     - Añadido índice único `payment_id` en SQLite para evitar duplicados en reinicios o sincronizaciones recurrentes (`INSERT OR IGNORE`).
  3. **Auto-Sincronización en el Arranque (`LiveCarryExecutor.sync_funding_history`):**
     - Cada vez que el bot arranca en modo real, sincroniza automáticamente cualquier cobro pendiente de KuCoin antes de comenzar el bucle.
  4. **Herramienta CLI de Sincronización Manual (`scripts/sync_funding.py`):**
     - Permite volcar e inspeccionar el historial completo de KuCoin a SQLite en cualquier instante con `python scripts/sync_funding.py`.
* **Resultado Esperado:** Reconstrucción contable 100% exacta y retroactiva desde el 31 de agosto de 2026, reflejando el histórico completo (+0.4024 USDT) en el dashboard y en los informes.

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
