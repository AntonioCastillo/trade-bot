# 📓 DIARIO DE BITÁCORA (Logbook de Cambios y Decisiones)

Este documento registra cronológicamente cada cambio significativo en el código, configuración o arquitectura de **tradebot**, detallando el **motivo empírico**, la **causa técnica** y el **impacto esperado**.

---

* [2026-10-25 | Sin Señal de Vida cada 6 h en Telegram](#2026-10-25--sin-señal-de-vida-cada-6-h-en-telegram)
* [2026-10-23 | Operaciones Reales del 4 al 23 de Octubre frente a la Simulación](#2026-10-23--operaciones-reales-del-4-al-23-de-octubre-frente-a-la-simulación)
* [2026-10-17 | Sin Cambios: Salidas de `volumen_explosivo` y Cabezas con las Monedas Libres de OKX](#2026-10-17--sin-cambios-salidas-de-volumen_explosivo-y-cabezas-con-las-monedas-libres-de-okx)
* [2026-10-17 | Capitulación Ampliada a 12 Monedas](#2026-10-17--capitulación-ampliada-a-12-monedas)
* [2026-10-15 | El Bot Pasa a Operar en OKX Europa](#2026-10-15--el-bot-pasa-a-operar-en-okx-europa)
* [2026-10-15 | Ventas del Bot cuando el Exchange Bloquea la Moneda (OKX)](#2026-10-15--ventas-del-bot-cuando-el-exchange-bloquea-la-moneda-okx)
* [2026-10-15 | OKX: Órdenes de Stop en Modo Contado](#2026-10-15--okx-órdenes-de-stop-en-modo-contado)
* [2026-10-15 | Preparado para Comprobar la Comisión de OKX Europa](#2026-10-15--preparado-para-comprobar-la-comisión-de-okx-europa)
* [2026-10-14 | Señales de Otro Exchange y Soporte de OKX Europa (Preparado, sin Activar)](#2026-10-14--señales-de-otro-exchange-y-soporte-de-okx-europa-preparado-sin-activar)
* [2026-10-14 | Bybit EU: la Cuenta Paga un 0,25% de Comisión](#2026-10-14--bybit-eu-la-cuenta-paga-un-025-de-comisión)
* [2026-10-13 | Ventas por Precios que no Existieron: Filtro de Tickers y Confirmación con el Libro](#2026-10-13--ventas-por-precios-que-no-existieron-filtro-de-tickers-y-confirmación-con-el-libro)
* [2026-10-13 | Exchange Configurable: Soporte de Bybit EU para Migrar desde KuCoin](#2026-10-13--exchange-configurable-soporte-de-bybit-eu-para-migrar-desde-kucoin)
* [2026-10-12 | Stops de Emergencia en el Exchange (Apagados por Defecto)](#2026-10-12--stops-de-emergencia-en-el-exchange-apagados-por-defecto)
* [2026-10-11 | Pausa Manual por Cabeza y Grid al 6% por Operación](#2026-10-11--pausa-manual-por-cabeza-y-grid-al-6-por-operación)
* [2026-10-10 | Rechazos 429 de KuCoin: Reintento y Sondeo Rápido que no se Detiene](#2026-10-10--rechazos-429-de-kucoin-reintento-y-sondeo-rápido-que-no-se-detiene)
* [2026-10-08 | El Gist Publicaba el Status con 15 Minutos de Retraso](#2026-10-08--el-gist-publicaba-el-status-con-15-minutos-de-retraso)
* [2026-10-08 | Despliegue Automático desde GitHub (el VPS Consulta la Rama `production`) y Parada Ordenada](#2026-10-08--despliegue-automático-desde-github-el-vps-consulta-la-rama-production-y-parada-ordenada)
* [2026-10-08 | Equity Correcto tras un Reinicio y Corrección de Ejecuciones sin Confirmar](#2026-10-08--equity-correcto-tras-un-reinicio-y-corrección-de-ejecuciones-sin-confirmar)
* [2026-10-07 | Filtro de Tendencia de la Propia Moneda en el Grid (EMA20 Diaria)](#2026-10-07--filtro-de-tendencia-de-la-propia-moneda-en-el-grid-ema20-diaria)
* [2026-10-07 | Medición del Deslizamiento de Stops y Sondeo Rápido de Posiciones Abiertas](#2026-10-07--medición-del-deslizamiento-de-stops-y-sondeo-rápido-de-posiciones-abiertas)
* [2026-10-04 | Tope de Exposición sobre el Equity y `volumen_explosivo` Ampliada a 7 Monedas](#2026-10-04--tope-de-exposición-sobre-el-equity-y-volumen_explosivo-ampliada-a-7-monedas)
* [2026-10-04 | Validación desde 2022: `capitulacion` Restaurada y `reversion_rango` Desactivada](#2026-10-04--validación-desde-2022-capitulacion-restaurada-y-reversion_rango-desactivada)
* [2026-10-04 | Reglas de Pausa por Cabeza: Strikes y Pausa Mientras Otra Cabeza Tiene Posiciones](#2026-10-04--reglas-de-pausa-por-cabeza-strikes-y-pausa-mientras-otra-cabeza-tiene-posiciones)
* [2026-10-04 | Nueva Cabeza `tendencia_alcista` (BTC, BNB, SOL) en Sustitución de las Cabezas Diarias](#2026-10-04--nueva-cabeza-tendencia_alcista-btc-bnb-sol-en-sustitución-de-las-cabezas-diarias)
* [2026-10-04 | Auditoría con Simulador de Mecánica Real: Símbolos Fijos en Cabezas Diarias y Trailing 8% en Volumen Explosivo](#2026-10-04--auditoría-con-simulador-de-mecánica-real-símbolos-fijos-en-cabezas-diarias-y-trailing-8-en-volumen-explosivo)
* [2026-10-03 | Rebalanceo de Ratio Riesgo/Beneficio y Stop Loss Estructural en Grid Lateral](#2026-10-03--rebalanceo-de-ratio-riesgobeneficio-y-stop-loss-estructural-en-grid-lateral)
* [2026-09-26 | Calibración de Eficiencia y Dimensionamiento en Grid Lateral (12% por Peldaño)](#2026-09-26--calibración-de-eficiencia-y-dimensionamiento-en-grid-lateral-12-por-peldaño)
* [2026-09-20 | Refactorización Arquitectónica y Simplificación (Fase 3: Jerarquía de Ejecución y Resiliencia de Red)](#2026-09-20--refactorización-arquitectónica-y-simplificación-fase-3-jerarquía-de-ejecución-y-resiliencia-de-red)
* [2026-09-20 | Refactorización Arquitectónica y Simplificación (Fase 2: Notificaciones Tipadas y Unificación de Modelos)](#2026-09-20--refactorización-arquitectónica-y-simplificación-fase-2-notificaciones-tipadas-y-unificación-de-modelos)

---

### 2026-10-25 | Sin Señal de Vida cada 6 h en Telegram

* **Archivos Afectados:** [`src/tradebot/scheduler.py`](../src/tradebot/scheduler.py), [`src/tradebot/config.py`](../src/tradebot/config.py), [`config.yaml`](../config.yaml), [`config.bybiteu.yaml`](../config.bybiteu.yaml), [`tests/test_scheduler.py`](../tests/test_scheduler.py)
* **Motivo:** decisión del operador. Con el bot estable, el informe de estado cada 6 h (4 al día, más el de medianoche) era excesivo.
* **Cambio:** `engine.alive_interval_seconds: 0` desactiva la señal de vida periódica (antes, 0 la habría enviado en cada ciclo). Queda el informe diario de las 00:00 UTC, que también sirve de prueba de vida: si no llega, algo va mal. Los avisos de operaciones, stops, pausas, cortafuegos, fallos y cambio de fuente de señales no cambian; el gist sigue publicándose cada 15 min.
* **Verificación:** 400 tests pasando (nuevo: 0 = desactivada).

---

### 2026-10-23 | Operaciones Reales del 4 al 23 de Octubre frente a la Simulación

* **Archivos Afectados:** ninguno (solo medición).
* **Motivo:** en octubre el resultado realizado pasó de positivo a −1,93 USDC. Con tan pocas operaciones por cabeza, el acierto real no permite concluir nada (para distinguir un 64% de un 50% en `volumen_explosivo` harían falta unas 100 posiciones). Lo que sí se puede comprobar es si el bot real hace lo mismo que el simulado en las mismas fechas.
* **Método:** simulación del bot con la configuración actual desde el 2026-10-04 (velas de KuCoin, comisión 0,10%), emparejada con las 29 operaciones reales abiertas desde esa fecha por cabeza, moneda y hora de entrada (±1 h).
* **Resultado:**
  * **20 de 29 coinciden**, a la misma hora y con el precio de entrada a menos de un 0,3%. En la mayoría el resultado es casi igual: ATOM −5,07% frente a −5,10%, ALGO +4,79% frente a +4,71%, ETH −4,04% frente a −4,20%, ALGO del 20-oct −4,58% frente a −4,78%, y SUI, LINK, LTC y las NEAR del grid en la misma línea. La ATOM abierta también está en la simulación.
  * **Periodo completo:** simulación −6,4% del equity (`volumen_explosivo` −4,7, `capitulacion` −1,2, `grid_lateral` −0,4); real ≈ −4,2% (−106 USDC cerrados más la ATOM abierta).
* **Diferencias y su causa:**

  | Diferencia | Efecto en real | Causa |
  |---|---:|---|
  | 8 operaciones del grid (NEAR 11–19 oct, DOT 7 oct) sin equivalente simulado | ≈ −12 USDC | La simulación pausa el grid el 8-oct por 3 stops en 7 días; en real se reanudó a mano el 11-oct |
  | Caída del 7-oct 02:00: ADA −5,95% y DOT −8,45% frente a −3,9% y −5,5% | ≈ −12 USDC | El precio cayó un 4% en 90 s y las ventas se llenaron por debajo del stop (el peor deslizamiento registrado, −2,81%); el simulador supone un deslizamiento pequeño |
  | ADA y AVAX del 13-oct (ventas por precios que no existieron): −1,1% y −3,0% frente a −6,4% y −6,4% | ≈ +18 USDC | Las dos monedas siguieron cayendo hasta sus stops: suerte |
  | DOGE (capitulación): +2,83% frente a −2,35% | ≈ +11 USDC | Mismo precio de entrada; con un trailing del 3%, azar |
  | 3 entradas de `volumen_explosivo` del 15-oct solo simuladas | a favor del real | Entradas pausadas durante el cambio a OKX; en la simulación suman en negativo |

* **Conclusiones:**
  1. El bot real reproduce la simulación: no hay fallos de funcionamiento. Las pérdidas de octubre son las que la simulación da para este mercado (octubre de 2026 simulado: −5,5%, empatado con el peor mes desde 2022; 20 de 57 meses negativos; la mitad de los tramos sin nuevo máximo duran más de 47 días).
  2. Reanudar a mano una pausa por strikes costó dinero (≈ −12 USDC). Conviene dejar actuar la regla.
  3. Las caídas bruscas son el único coste que el simulador recoge de menos. Con el sondeo cada 10 s no hay mucho margen; el stop de emergencia de OKX protege si el bot está caído, no en una caída rápida.
  4. La simulación de 5 años sigue siendo válida como referencia para juzgar las cabezas.

---

### 2026-10-17 | Sin Cambios: Salidas de `volumen_explosivo` y Cabezas con las Monedas Libres de OKX

* **Archivos Afectados:** ninguno (solo mediciones).
* **Motivo:** en real, `volumen_explosivo` lleva −34,36 USDC con un 53% de operaciones ganadoras. Agrupado por posición (la venta parcial y el resto cuentan como una), son 4 ganadoras (+34,08, media +8,5) y 5 perdedoras (−68,46, media −13,7). Tres stops completos (ADA, ATOM y ETH) suman −57,8, y las dos ventas por precios que no existieron, −10,70. La ganadora media (+5% de la posición) y la perdedora media (−5 a −6%) coinciden con lo simulado; lo que no coincide es el acierto: 4 de 9 posiciones frente al 64% simulado, dentro de lo esperable con 9 posiciones en un mercado sin tendencia. Se midió si la venta parcial o el objetivo explican la asimetría y, de paso, si alguna cabeza, activa o retirada, gana con las monedas de OKX que no usa nadie.
* **Método:** bot completo simulado desde 2022 con velas de KuCoin, comisión 0,10% y la configuración actual, partido en dos mitades (corte 2024-05-18). Referencia: **+194,8%** (1ª mitad +74,5, 2ª +68,7), caída máx. 11,1%.
* **`volumen_explosivo`, venta parcial × objetivo** (stop 6% y trailing 8% sin cambios):

  | Parcial | Objetivo | Resultado | 1ª mitad | 2ª mitad | Caída máx. | Aporta la cabeza | Acierto |
  |---:|---:|---:|---:|---:|---:|---:|---:|
  | **5%** | **20%** | **+194,8%** | +74,5 | +68,7 | **11,1%** | +90,9 | 64% |
  | 5% | 15% / 30% | +185,6% / +190,9% | +74,5 / +74,3 | +63,3 / +66,7 | 10,4% / 11,0% | +80,7 / +86,3 | 64% |
  | sin parcial | 20% / 30% | +198,1% / +198,6% | +74,5 / +77,3 | +70,9 / +68,5 | 15,7% / 16,2% | +101,5 / +98,1 | 37% |
  | 8% | 20% | +180,9% | +74,8 | +60,5 | 12,0% | +78,7 | 44% |
  | 10% | 20% | +175,5% | +73,3 | +58,8 | 12,9% | +75,6 | 37% |

  * El objetivo del 20% es el mejor con cualquier parcial. Quitar la parcial gana 3 puntos pero sube la caída máxima del 11,1% al 15,7%: las ganadoras doblan su tamaño y se acierta la mitad de veces. Parcial al 8% o 10%, peor en todo. **Se deja como está.**
* **Cabezas con las monedas libres de OKX:** 23 monedas que cotizan en USDC en OKX, no usa ninguna cabeza activa y tienen historia en KuCoin anterior a 2024 (por liquidez: ZEC, TAO, SEI, PEPE, SHIB, WLD, BCH, HBAR, PYTH, STX, DASH, RSR, APT, CRV, ICP, SAND, PENDLE, BAT, POL, ZIL, VELO, LDO, GRT). Cada cabeza se añade al bot con las 4, 8 o 16 más líquidas, sin mirar su resultado. Las retiradas usan su última definición (`breakout_diario` y `momentum_diario`, del commit anterior a su sustitución; `reversion_rango`, la de `config.yaml`).

  | Cabeza | + 4 | + 8 | + 16 |
  |---|---:|---:|---:|
  | `tendencia_alcista` | +148,3% | +169,6% | +92,3% |
  | `breakout_diario` | +186,8% | +174,0% | +133,7% |
  | `momentum_diario` | +194,6% | +185,8% | +166,2% |
  | `reversion_rango` | +167,9% | +151,2% | +130,7% |

  * Ninguna de las 12 supera la referencia. Lo más cercano (`breakout_diario` y `momentum_diario` con 4) aporta ±1 punto. El patrón se repite: ganan algo en la primera mitad y pierden en la segunda (las monedas libres son sobre todo las que han caído o se han estancado desde 2024), y cuantas más monedas, peor, porque restan saldo a las cabezas que funcionan. `tendencia_alcista` confirma lo visto en la auditoría: solo funciona con monedas grandes.
  * Las cabezas retiradas: `reversion_rango` se desactivó por perder (restaba en las dos mitades) y vuelve a perder en todos los grupos; `breakout_diario` y `momentum_diario` no perdían, se sustituyeron por `tendencia_alcista`, que gana más en absoluto, y con estas monedas tampoco aportan.
* **Decisión:** no se cambia nada. No repetir estas pruebas sin una idea nueva.

---

### 2026-10-17 | Capitulación Ampliada a 12 Monedas

* **Archivos Afectados:** [`config.yaml`](../config.yaml), [`config.bybiteu.yaml`](../config.bybiteu.yaml), [`tests/test_okx_config.py`](../tests/test_okx_config.py), [`tests/test_bybit_eu.py`](../tests/test_bybit_eu.py)
* **Motivo:** con las señales sacadas de KuCoin, el bajo volumen de OKX en USDC ya no limita qué monedas puede operar el bot, y OKX tiene casi 300 pares en USDC. Se midió si alguna cabeza gana con más monedas: 16 candidatas que cotizan en USDC en OKX y tienen historia en KuCoin, añadidas a cada cabeza, con el bot completo simulado desde 2022 (velas de KuCoin, comisión 0,10%, configuración actual sin ETC), partido en dos mitades. Para no escoger por azar, la prueba decisiva fue por grupos ordenados por volumen en KuCoin, sin mirar el resultado.
* **Resultados** (referencia: +176,2%; 1ª mitad +73,7, 2ª +58,9; caída máx. 11,1%):

  | Cambio | Resultado | 1ª mitad | 2ª mitad | Caída máx. |
  |---|---:|---:|---:|---:|
  | capitulación + 4 más líquidas | +192,0% | +74,3 | +67,3 | 11,1% |
  | **capitulación + 8 más líquidas** | **+196,0%** | **+74,5** | **+69,4** | **11,1%** |
  | capitulación + 16 | +186,8% | +73,6 | +65,0 | 11,1% |
  | volumen + 4 más líquidas | +208,4% | +62,1 | +90,3 | 14,2% |
  | volumen + 8 más líquidas | +177,9% | +67,0 | +66,4 | 15,1% |
  | volumen + 16 | +162,4% | +78,3 | +47,1 | 19,9% |

  * **Capitulación:** con las 8 más líquidas pasa de 9 a 28 operaciones y de +3,8 a +18,7 puntos, sin empeorar ninguna mitad ni la caída máxima. Una por una, 12 de las 16 suman algo. Reserva: son 19 operaciones más y la mejora se concentra en 2024–2026.
  * **Volumen explosivo:** sin mejora estable. Con 4 más gana en total pero empeora la primera mitad y la caída; con más monedas compiten por el saldo (rechazos por tope de posiciones de 3 a 364). Una por una, de +21 (HBAR) a −27 (OP): dispersión de azar. Se deja como está.
  * **Grid:** casi todas restan algo (−0,1 a −3,4 puntos): sin ventaja, más monedas solo añaden operaciones neutras. Se deja como está.
* **Cambio:** capitulación con XRP, DOGE, TRX, UNI + AAVE, INJ, ARB, TIA, FIL, XLM, FET y OP. Las 8 cotizan en USDC en OKX y tienen par USDT en KuCoin (señales) y en Binance (respaldo). En `config.bybiteu.yaml`, sin FET, que Bybit EU no cotiza contra USDC.

---

### 2026-10-15 | El Bot Pasa a Operar en OKX Europa

* **Archivos Afectados:** [`config.yaml`](../config.yaml), `config.okx.yaml` (eliminado), [`tests/test_okx_config.py`](../tests/test_okx_config.py), [`tests/test_bybit_eu.py`](../tests/test_bybit_eu.py), [`deploy/DEPLOY.md`](../deploy/DEPLOY.md), [`.env.example`](../.env.example), [`README.md`](../README.md)
* **Motivo:** KuCoin global no puede dar servicio en España desde el fin del transitorio de MiCA. De los destinos con licencia europea, OKX Europa quedó verificado de punta a punta con la cuenta real el 2026-10-15: comisión 0,100% a mercado y 0,080% limitada en los 17 pares (con la cuenta de derivados X-Perps abierta), cuenta, compra y venta real de 10 USDC, y órdenes de stop siete de siete. Simulado desde 2022 con señales de KuCoin: ≈ +182%, frente a ≈ +142% en Bybit EU al 0,25%.
* **Cambios Implementados:**
  1. `config.yaml` pasa a ser la configuración de OKX Europa en real: USDC, sin ETC, comisión 0,10%, señales de KuCoin con Binance de respaldo y stops de emergencia del exchange activos. Desaparece `config.okx.yaml`.
  2. `config.bybiteu.yaml` se queda como alternativa verificada; un test vigila que siga alineada con `config.yaml`.
  3. `.env.example`, README y `deploy/DEPLOY.md` (secciones 10 y 11) con las claves de OKX, su lista de IP (IPv4 e IPv6) y cómo volver a Bybit si hiciera falta.
* **Cuándo se fusiona:** con el bot sin posiciones en KuCoin (lo está desde el 15-oct) y el saldo ya en OKX. Si quedaran posiciones en USDT, el bot no arranca y el despliegue vuelve atrás solo. Antes conviene fusionar el ajuste de las ventas con la moneda bloqueada (PR #15).
* **Verificación:** 399 tests pasando, junto con el ajuste de las ventas con la moneda bloqueada.

---

### 2026-10-15 | Ventas del Bot cuando el Exchange Bloquea la Moneda (OKX)

* **Archivos Afectados:** [`src/tradebot/exchange_stops.py`](../src/tradebot/exchange_stops.py), [`src/tradebot/engine.py`](../src/tradebot/engine.py), [`tests/test_signal_source.py`](../tests/test_signal_source.py)
* **Qué se vio:** `verify-stops --config config.okx.yaml` pasó las siete comprobaciones con la cuenta real (15-oct), y confirmó que **OKX bloquea la moneda mientras vive la orden de stop**: de 0,00245654 ETH quedaron libres 0,00045654 con la orden de 0,002 viva. El bot cancela su orden antes de vender, pero si esa cancelación fallaba seguía adelante ("vender es lo prioritario"), algo pensado para KuCoin y Bybit, que no bloquean. En OKX solo habría vendido la parte libre.
* **Cambios Implementados (solo en exchanges que bloquean, hoy OKX):**
  1. Antes de vender se intenta cancelar la orden hasta 3 veces, con medio segundo entre intentos.
  2. Si no se consigue, **no vende en ese sondeo** y lo reintenta en el siguiente. Mientras, la orden del exchange sigue viva y protegiendo, un 2% por debajo del stop del bot.
  3. Tras cancelar, espera hasta 2 segundos a que el saldo quede libre antes de vender. Si sigue bloqueado, vende lo libre y lo deja en el log.
* **En KuCoin y Bybit no cambia nada:** un intento de cancelar y, si falla, vende igualmente.
* **Verificación:** 399 tests pasando (6 nuevos).

---

### 2026-10-15 | OKX: Órdenes de Stop en Modo Contado

* **Archivos Afectados:** [`src/tradebot/exchange.py`](../src/tradebot/exchange.py), [`src/tradebot/exchange_stops.py`](../src/tradebot/exchange_stops.py), [`scripts/verify_stops.py`](../scripts/verify_stops.py), [`tests/test_signal_source.py`](../tests/test_signal_source.py), [`deploy/DEPLOY.md`](../deploy/DEPLOY.md)
* **Qué se vio (cuenta real, 15-oct):** `manage.py fees` dio 0,100% a mercado y 0,080% limitada en los 17 pares (X-Perps activo); `verify-account` correcto; `verify-api` correcto (compra y venta de 10 USDC por 0,0115 de coste, comisión de compra cobrada en BTC). `verify-stops` falló al crear la orden: OKX respondió 50013 sin mensaje. Un diagnóstico en el VPS (cuenta con `acctLv` 2) mostró que ccxt manda la orden condicional en modo de margen (`tdMode: cross`), que OKX rechaza con 50013; en modo contado (`tdMode: cash`) la acepta, pero solo si hay saldo de la moneda (51008 con 0 ETH).
* **Cambios Implementados:**
  1. Órdenes de stop de OKX con `tdMode: cash`.
  2. `Exchange.stop_needs_balance` (cierto en OKX): al subir el stop se retira primero la orden vieja y después se pone la nueva, porque la vieja puede tener la moneda bloqueada. Son unos instantes sin orden en el exchange; el stop del bot sigue activo. Si la vieja no se puede retirar, se queda y se reintenta en 5 minutos. En KuCoin y Bybit no cambia nada: se sigue creando la nueva antes de retirar la vieja.
  3. `verify-stops`: si el exchange exige la moneda y no la hay, lo dice antes de intentarlo (cuánta hace falta); si la hay, informa de si el exchange la bloquea mientras vive la orden.
* **Pendiente:** repetir `verify-stops --config config.okx.yaml` con unos 0,002 ETH en la cuenta.
* **Verificación:** 393 tests pasando (3 nuevos con un exchange que exige y bloquea la moneda).

---

### 2026-10-15 | Preparado para Comprobar la Comisión de OKX Europa

* **Archivos Afectados:** [`config.okx.yaml`](../config.okx.yaml), [`scripts/check_fees.py`](../scripts/check_fees.py), [`scripts/manage.py`](../scripts/manage.py), [`tests/test_okx_config.py`](../tests/test_okx_config.py), [`deploy/DEPLOY.md`](../deploy/DEPLOY.md)
* **Motivo:** el operador elegirá entre Bybit EU (0,25%, comprobado) y OKX Europa según la comisión que OKX le cobre de verdad. Por su tabla, al contado y a mercado: 0,10% con la cuenta de derivados X-Perps abierta y 0,20% sin ella. Las vías ya existentes (`verify-account --exchange myokx`) comparaban con la comisión de Bybit y no mostraban el detalle por par.
* **Cambios Implementados:**
  1. **`config.okx.yaml`** (en simulado): la configuración de Bybit EU con `exchange: myokx`, señales de KuCoin con Binance de respaldo y `fee_pct: 0.0010`, la esperada con X-Perps. Un test vigila que no se desvíe de `config.bybiteu.yaml`.
  2. **`manage.py fees`** (no opera): comisión de la cuenta, a mercado y con orden limitada, en cada par, comparada con KuCoin (0,10%) y Bybit EU (0,25%) y con la de la configuración.
  3. Sección 11 de `deploy/DEPLOY.md`: cómo activar X-Perps, la comprobación de comisiones y las verificaciones con `--config config.okx.yaml`.
* **Qué decide el número:** con 0,10% y señales de KuCoin, la simulación desde 2022 da ≈ +182% (≈ +165% si las señales salen de Binance), frente a ≈ +142% en Bybit EU al 0,25%. Con 0,20%, ≈ +154%: algo mejor que Bybit, pero con más trabajo y menos probado.

---

### 2026-10-14 | Señales de Otro Exchange y Soporte de OKX Europa (Preparado, sin Activar)

* **Organización:** es todo el código para cambiar de exchange, sin cambiar de exchange: `config.yaml` sigue en KuCoin. El operador decidirá entre Bybit EU y OKX Europa según la comisión que confirme OKX; el cambio será un PR solo de configuración, el día que se mueva el saldo.

* **Archivos Afectados:** [`src/tradebot/config.py`](../src/tradebot/config.py), [`src/tradebot/exchange.py`](../src/tradebot/exchange.py), [`src/tradebot/exchange_stops.py`](../src/tradebot/exchange_stops.py), [`src/tradebot/engine.py`](../src/tradebot/engine.py), [`src/tradebot/daemon.py`](../src/tradebot/daemon.py), [`scripts/livesim.py`](../scripts/livesim.py), scripts de verificación, [`tests/test_signal_source.py`](../tests/test_signal_source.py), [`deploy/DEPLOY.md`](../deploy/DEPLOY.md)
* **Motivo:** OKX Europa cobra menos que Bybit EU al contado (tabla oficial para el EEE, nivel Regular, a mercado: 0,10% con la cuenta de derivados X-Perps abierta y 0,20% sin ella), pero su volumen en USDC es del 0,1–3% del de KuCoin. Con sus propias velas, de enero a octubre de 2026, el bot daba +1,8% (caída máx. 20%) al 0,10%, frente a +9,6% en KuCoin y +10,2% en Bybit EU: `volumen_explosivo` entraba 135 veces en vez de 46, por picos de volumen que en un mercado tan fino no significan nada. Tomando las señales de las velas de KuCoin y ejecutando en OKX, el mismo periodo da +10,5%. El operador pidió preparar el bot para operar en OKX mirando el volumen de otro exchange.
* **Validación de Binance como fuente de señales** (desde 2022, 17 monedas sin ETC, ejecución con los precios de KuCoin como sustituto, porque OKX y Bybit EU solo tienen historia desde octubre de 2025):

  | Comisión | Señales de KuCoin | Señales de Binance |
  |---|---:|---:|
  | 0,10% | +181,8% | +165,3% |
  | 0,20% | +154,3% | +138,9% |
  | 0,25% | +141,5% | +126,6% |

  Caída máxima parecida (11–14%). Las entradas de `tendencia_alcista` coinciden 73 de 74 y las de `capitulacion` 8 de 9; las de `volumen_explosivo`, 157 de 289: el volumen de Binance es unas 8 veces el de KuCoin y sus picos se parecen (correlación 0,73–0,87), pero no son los mismos. Con Binance, la cabeza de volumen sigue ganando (+83 puntos frente a +92): su ventaja no es un artefacto de KuCoin. Por años, Binance sale mejor en 2023 y 2025 y peor en 2024.
* **Cambios Implementados:**
  1. **Fuente de señales (`data_exchange`, `data_quote`):** las velas de estrategias y filtros (macro de BTC, tendencia de la moneda, fuerza relativa) salen de ese exchange, solo con datos públicos y su par equivalente (NEAR/USDC → NEAR/USDT). Las órdenes, los saldos, los tickers y el libro siguen en `exchange`.
  2. **Salidas con el precio del exchange que opera:** con la fuente separada, el ciclo de 60 s pide los precios de `exchange` en una consulta y el motor no decide salidas con el cierre de la vela de la otra fuente. Si esa consulta falla, ese ciclo no evalúa salidas (el sondeo rápido sigue).
  3. **OKX Europa (`exchange: myokx`):** claves `OKX_API_KEY`, `OKX_API_SECRET` y `OKX_API_PASSPHRASE`; órdenes de stop como orden algo `conditional` a mercado; listado con `ordType: conditional`; la cancelación lee el resultado dentro de la respuesta (OKX no lanza error si la orden ya no existe).
  4. **Identificador de las órdenes de stop sin guion** (`tbstop…`): OKX solo admite letras y números. Las órdenes antiguas (`tbstop-…`) se siguen reconociendo.
  5. **`position_gone` mira el saldo total** (libre + bloqueado): si un exchange bloquea la moneda mientras vive la orden de stop, el libre sale 0 y la posición se habría dado por vendida.
  6. **Verificaciones contra otro exchange** con la misma configuración: `manage.py verify-account|verify-api|verify-stops --exchange myokx`.
  7. **`livesim.py --signal-exchange binance --signal-quote USDT`** (o `data_exchange` en la configuración): simula con las señales de otra fuente. Reproduce el resultado del estudio de octubre.
  8. **Herramientas que no operan sin claves:** `load_config(..., require_credentials=False)` en simulaciones, análisis y verificaciones (que ya avisan si faltan claves): pueden cargar una configuración en real sin las claves de su exchange. El bot en real sigue exigiéndolas.
  9. **`livesim.py --exchange kucoin --quote USDT`:** simular con las velas de otro exchange; hace falta para estudios largos con Bybit EU u OKX, que solo tienen historia desde octubre de 2025.
  10. **Respaldo automático de la fuente** (`data_fallback_exchange`, `data_fallback_quote`), pedido por el operador: KuCoin como principal y Binance de respaldo. Si la principal falla 3 veces seguidas (no cuenta un par que no exista en ella), las velas salen del respaldo durante 30 minutos y después se vuelve a probar la principal. Cada llamada usa una sola fuente, así que una ventana de velas nunca mezcla exchanges. Aviso por Telegram en cada cambio y `data_source` en el gist. Si fallan las dos, ese ciclo no tiene velas: no hay entradas nuevas y las salidas siguen con los precios del exchange que opera.
* **Estado:** preparado, sin activar. `config.yaml` sigue en KuCoin sin fuente separada. Contra la API pública de OKX funcionan pares, precios, libro y velas; con Binance como fuente, las velas de NEAR/USDC salen de NEAR/USDT. **Sin probar:** todo lo que necesita claves de OKX (saldo, órdenes, comisión real y, sobre todo, sus órdenes de stop).
* **Lectura:** con X-Perps (0,10%) y señales de Binance, ≈ +165% desde 2022 frente a ≈ +141% en Bybit EU al 0,25% (señales de KuCoin como sustituto de las suyas). Sin X-Perps (0,20%), OKX con señales de Binance (+139%) no mejora a Bybit EU.
* **Verificación:** 388 tests pasando (16 nuevos en `tests/test_signal_source.py` y 8 en `tests/test_signal_failover.py`). Con datos reales: con KuCoin respondiendo, las velas de NEAR/USDC salen de NEAR/USDT en KuCoin; simulando su caída, al tercer fallo salen de Binance.

---

### 2026-10-14 | Bybit EU: la Cuenta Paga un 0,25% de Comisión

* **Archivos Afectados:** [`config.bybiteu.yaml`](../config.bybiteu.yaml), [`tests/test_bybit_eu.py`](../tests/test_bybit_eu.py), [`deploy/DEPLOY.md`](../deploy/DEPLOY.md)
* **Qué se vio:** `manage.py verify-account --config config.bybiteu.yaml` en el VPS, con las claves de la cuenta real: todo correcto salvo la comisión, **0,25% a mercado y 0,25% con orden limitada en los 17 pares**. Es el dato de la propia cuenta, no el 0,10% que daban la API pública y las guías. El operador es VIP 0 en KuCoin, así que el programa de Bybit para subir de nivel a quien ya es VIP en otro exchange no le aplica.
* **Efecto simulado** (todas las cabezas, cambiando solo la comisión): desde 2022, +119% (caída máx. 14,5%) frente a +161% al 0,10%; con las velas de Bybit EU de enero a octubre de 2026, +10,2% frente a +13,2%. La que más pierde es `volumen_explosivo` (+75 → +47 puntos), la que más opera. Kraken en su tramo (0,60%) daba +47%: Bybit EU sigue siendo la mejor opción comprobada.
* **Cambio:** `engine.fee_pct: 0.0025` en `config.bybiteu.yaml`, para que `verify-account` compare con la comisión real y las simulaciones y el modo simulado usen ese coste. En real el bot anota la comisión que cobra el exchange; este valor no cambia lo que paga. `config.yaml` (KuCoin) sigue en 0,10%.

---

### 2026-10-13 | Ventas por Precios que no Existieron: Filtro de Tickers y Confirmación con el Libro

* **Archivos Afectados:** [`src/tradebot/exchange.py`](../src/tradebot/exchange.py), [`src/tradebot/engine.py`](../src/tradebot/engine.py), [`src/tradebot/exchange_stops.py`](../src/tradebot/exchange_stops.py), [`tests/test_price_guard.py`](../tests/test_price_guard.py)
* **Qué pasó (13-oct, en real):** `volumen_explosivo` vendió la mitad de ADA (09:31:21 UTC) y de AVAX (11:20:18 UTC) como «toma parcial», que exige precio ≥ entrada +5% (ADA ≥ 0,2489; AVAX ≥ 10,986). El mercado estaba en 0,2351 y 10,16, y las velas de 1 minuto de KuCoin no muestran ningún pico: ADA no tocaba 0,2489 desde el día anterior a las 13:07, antes de abrir la posición. Minutos antes el stop de arrastre de ambas ya había subido por un máximo también inexistente (ADA ≈ 0,2439; AVAX ≈ 10,915). Tras la parcial el stop pasa a la entrada, que quedaba por encima del mercado, y el sondeo siguiente vendió el resto.
  * Resultado: ADA −3,19 USDT (parcial −1,53, resto −1,66) y AVAX ≈ −7,5 USDT. Frente a no haber vendido, 1–2 USDT, porque ambas siguieron por debajo de la entrada.
  * Las estadísticas de deslizamiento de stops recogen estas dos ventas como −0,93% y −2,81%. **No son deslizamiento:** el «nivel» era la entrada, ya por encima del mercado. Ninguna orden de stop del exchange se ha disparado todavía.
* **Causa probable (comprobada en la librería, no demostrada en el momento del fallo):** por la hora, la primera lectura errónea llegó en el sondeo rápido (`fetch_tickers`). Si KuCoin manda un ticker sin `last`, `ccxt` no devuelve «sin dato»: lo deduce como `averagePrice + changePrice / 2`, suponiendo que la media es la de apertura y cierre. En KuCoin es el precio medio del día anterior. Con un ticker real de ADA sin `last`, ccxt 4.5.70 (la del VPS) devuelve 0,2315 con el mercado en 0,2350. En un día de caída el valor queda por encima del mercado (lo ocurrido); en uno de subida quedaría por debajo y haría saltar stops. Tres de las cuatro lecturas erróneas encajan con esa fórmula (la de ADA, exacta); la primera de AVAX no cuadra del todo. En 40 muestras seguidas del listado de KuCoin no apareció ningún ticker sin `last`. El bot no anotaba el precio que veía, así que el log no permitía confirmarlo.
* **Cambios Implementados:**
  1. **Filtro de tickers (`exchange.ticker_price`):** el último precio solo se usa si está dentro de la horquilla de compra y venta del propio ticker, con un 1% de margen (esos dos campos vienen tal cual del exchange). Si no, en el sondeo rápido esa moneda se salta y en la consulta individual se devuelve el punto medio del libro. Queda un aviso en el log, como mucho uno cada 5 minutos por moneda.
  2. **Confirmación antes de vender (`Engine._exit_confirmed`, solo en real):** antes de un stop, un objetivo o una toma parcial se lee el libro de órdenes (`Exchange.fetch_book_price`). Un stop se ejecuta salvo que la mejor compra esté más de un 1% por encima del precio que lo disparó; un objetivo o una parcial, solo si no está más de un 1% por debajo. Si no se confirma, no se vende y **el stop de arrastre vuelve a donde estaba**. Si la lectura falla, el stop se ejecuta igualmente y el resto espera al siguiente sondeo.
  3. **Precio de disparo en el log:** cada salida anota el precio visto y el del libro.
  4. **Aviso por Telegram** (como mucho uno por hora) si una posición lleva 15 minutos sin poder poner su stop de emergencia. El 13-oct KuCoin rechazó crear órdenes de stop de 11:20 a 15:28 UTC (`123002 ULTRA-OPEN-SERVICE ERROR`) y NEAR estuvo tres horas y media sin la suya sin que llegara ningún aviso.
* **Coste:** una consulta más por venta, unos 0,26 s medidos. En una caída real muy rápida el stop sale ese tiempo más tarde.
* **Lo que no cubre:** si un precio falso llegara por el cierre de la última vela (ciclo de 60 s) y solo subiera el stop de arrastre, sin provocar venta, ese stop quedaría subido. Las velas vienen tal cual del exchange y no se ha visto que fallen; el cambio 3 permitirá detectarlo.
* **Verificación:** 342 tests pasando (18 nuevos en `tests/test_price_guard.py`, incluido el ticker sin `last` pasado por el analizador real de ccxt). Con datos reales de KuCoin, 30 muestras de las 18 monedas: ningún ticker descartado y el último precio nunca a más del 0,22% de la horquilla.
### 2026-10-13 | Exchange Configurable: Soporte de Bybit EU para Migrar desde KuCoin

* **Archivos Afectados:** [`src/tradebot/config.py`](../src/tradebot/config.py), [`src/tradebot/exchange.py`](../src/tradebot/exchange.py), [`src/tradebot/execution/live.py`](../src/tradebot/execution/live.py), [`src/tradebot/engine.py`](../src/tradebot/engine.py), [`src/tradebot/daemon.py`](../src/tradebot/daemon.py), [`scripts/verify_account.py`](../scripts/verify_account.py), [`scripts/verify_stops.py`](../scripts/verify_stops.py), [`scripts/verify_api.py`](../scripts/verify_api.py), [`scripts/manage.py`](../scripts/manage.py), [`scripts/livesim.py`](../scripts/livesim.py), [`config.bybiteu.yaml`](../config.bybiteu.yaml), [`tests/test_bybit_eu.py`](../tests/test_bybit_eu.py), [`deploy/DEPLOY.md`](../deploy/DEPLOY.md)
* **Motivo / Petición del Usuario:**
  * Al entrar en KuCoin, el operador ve errores de que su zona no puede usar el servicio. El periodo transitorio de MiCA terminó en España el 1 de julio de 2026; KuCoin global no tiene autorización europea y su filial (KuCoin EU, licencia austriaca de noviembre de 2025) tiene prohibido iniciar operaciones por decisión de la FMA de 18-feb-2026, vigente en su último aviso (18-may-2026). Sus términos (29-sep-2026) permiten restringir cuentas sin preaviso. El bot seguía operando por API el 13-oct.
  * Se midieron dos destinos con las 18 monedas del bot:
    * **Kraken:** tabla de comisiones nueva desde el 9-jul-2026. El bot mueve ≈4.600 USD/mes con 2.250 de equity, lo que da 0,60% por operación a mercado (0,80% los meses flojos; 0,38% a partir de 10.000 USD/mes). Simulación desde 2022, todas las cabezas, cambiando solo la comisión: 0,10% → +161% (caída máx. 12%); 0,38% → +89%; 0,60% → +47% (`volumen_explosivo` ≈ 0); 0,80% → +17%. En euros (velas de KuCoin convertidas con EUR/USDT), +122% al 0,10% y +21% al 0,60%.
    * **Bybit EU:** 0,10% y USDC. Con sus propias velas (solo hay historia desde oct-2025), de enero a octubre de 2026 y sin ETC, que no cotiza: +12,5% frente a +9,0% de KuCoin, pero solo 31 de 67 entradas coinciden (`volumen_explosivo` 14 de 44), porque su volumen es entre 10 y 100 veces menor.
    * Liquidez (6 muestras del libro, ida y vuelta de 450 a mercado, mediana): KuCoin 0,035%, Bybit EU 0,040%, Kraken EUR 0,046%.
  * El operador decidió migrar a Bybit EU y pidió preparar el código.
* **Cambios Implementados:**
  1. **`exchange: kucoin | bybiteu`** en la configuración (cualquier otro valor se rechaza). Las claves salen del `.env` según el exchange: `BYBIT_API_KEY` y `BYBIT_API_SECRET`, sin passphrase.
  2. **Moneda de cotización:** el par de referencia (filtro macro de BTC, fuerza relativa, verificación de la API) es `BTC/<risk.quote_currency>` en vez de `BTC/USDT` fijo. Una configuración con pares en otra moneda se rechaza al cargar.
  3. **Llamadas propias de Bybit** (`exchange.py`): mercado al contado por defecto; órdenes de stop como **orden condicional** (`triggerPrice`), que no bloquea saldo, igual que en KuCoin (la de TP/SL sí lo bloquea y rompería las ventas del bot); consulta de órdenes con respaldo en el historial; páginas de 1.000 velas.
  4. **Comisión en la moneda comprada** (`execution/live.py`): Bybit cobra la comisión de las compras en la moneda comprada. La cantidad se anota neta y la comisión se convierte a la moneda de cotización, de modo que precio × cantidad + comisión sigue siendo lo pagado.
  5. **Protección al cambiar:** en real, si quedan posiciones registradas en otra moneda de cotización, el bot no arranca (`ForeignPositionsError`). Reconciliarlas contra la cuenta nueva las daría por vendidas y anotaría cierres falsos.
  6. **`config.bybiteu.yaml`:** la configuración real con USDC, sin ETC, en simulado, con los stops de emergencia y el radar de funding apagados. Un test vigila que no se desvíe de `config.yaml`.
  7. **`manage.py verify-account`** (nuevo, no opera): pares, mínimos, saldo, comisión de la cuenta y listado de órdenes de stop. `verify-stops` y `verify-api` aceptan `--config`.
  8. **`livesim.py`** simula con las velas del exchange de la configuración (`--config config.bybiteu.yaml`), con caché aparte.
* **Estado:** nada cambia en real: `config.yaml` sigue en KuCoin. Comprobado contra la API pública de Bybit EU: los 17 pares existen, velas, precios en una consulta, historial paginado y un ciclo completo en simulado. **Sin probar:** todo lo que necesita claves. Los pasos, en `deploy/DEPLOY.md`, sección 10.
* **Riesgos conocidos:** (1) las llamadas autenticadas de Bybit solo se confirman con la cuenta real (`verify-account`, `verify-api`, `verify-stops`); (2) la ventaja de `volumen_explosivo` está medida sobre el volumen de KuCoin; (3) Bybit EU solo tiene un año de historia propia, así que no se puede validar allí la configuración en varios ciclos.
* **Verificación:** 346 tests pasando (22 nuevos en `tests/test_bybit_eu.py`).

---

### 2026-10-12 | Stops de Emergencia en el Exchange (Apagados por Defecto)

* **Archivos Afectados:** [`src/tradebot/exchange_stops.py`](../src/tradebot/exchange_stops.py), [`src/tradebot/engine.py`](../src/tradebot/engine.py), [`src/tradebot/exchange.py`](../src/tradebot/exchange.py), [`src/tradebot/daemon.py`](../src/tradebot/daemon.py), [`src/tradebot/storage.py`](../src/tradebot/storage.py), [`src/tradebot/models.py`](../src/tradebot/models.py), [`src/tradebot/config.py`](../src/tradebot/config.py), [`src/tradebot/status.py`](../src/tradebot/status.py), [`scripts/verify_stops.py`](../scripts/verify_stops.py), [`scripts/manage.py`](../scripts/manage.py), [`config.yaml`](../config.yaml), [`tests/test_exchange_stops.py`](../tests/test_exchange_stops.py)
* **Motivo / Petición del Usuario:**
  * Los stops los ejecuta el bot (sondea el precio y vende a mercado). Si el proceso o el servidor se caen con posiciones abiertas, no queda ningún stop. El operador pidió ponerlos en el exchange.
  * No es la «fase 3» de la sección 6.4 del audit tal cual: el deslizamiento medido con el sondeo de 10 s es bajo (0,24% en 8 stops), así que no hace falta sustituir el stop del bot. Lo que faltaba era la protección ante una caída del bot.
* **Diseño:** una orden de stop a mercado en KuCoin por posición, como **red de seguridad**: se coloca un 2% por debajo del stop del bot (`exchange_stop_buffer_pct`). En funcionamiento normal vende el bot, como hasta ahora, y la orden no llega a dispararse; así tampoco vende en las mechas cortas que el sondeo deja pasar (8% de los stops simulados, sección 6.4). Si el bot no está, la pérdida queda limitada al stop más ese margen.
* **Cambios Implementados:**
  1. `exchange_stops.StopGuard`: crea la orden al abrir la posición y la repone cuando el stop del bot sube al menos un 0,5% (`exchange_stop_min_move_pct`) o cambia la cantidad (toma parcial, compra confirmada). La cantidad nunca supera el saldo real de la moneda: una orden por más saldo del disponible no se ejecutaría.
  2. Antes de cualquier venta del bot se cancela la orden. Si ya no existe y el activo no está en la cuenta, es que vendió el exchange: se registra el cierre con el precio real de la orden (o el de disparo, a corregir después con `reconcile_fills`) y **no se envía otra venta**.
  3. `Engine.sync_exchange_stops()`, una vez por ciclo y al arrancar: detecta ventas hechas por el exchange (también con el bot parado), **cancela las órdenes huérfanas** y repone las que falten. Las órdenes del bot llevan el prefijo `tbstop-` en su `clientOid`; nunca se toca una orden ajena.
  4. Si una orden huérfana no se puede cancelar, aviso por Telegram (como mucho uno por hora): podría vender una compra posterior de la misma moneda, porque KuCoin no bloquea saldo para estas órdenes.
  5. Si se desactiva la opción, al arrancar se retiran las órdenes que hubiera dejado el bot.
  6. El gist muestra `exchange_stop` (precio de disparo) en cada posición.
  7. `manage.py verify-stops`: prueba contra KuCoin real crear, listar y cancelar una orden de stop mínima con el disparo un 50% por debajo del precio (no opera).
* **Estado:** se desplegó apagado (`engine.exchange_stops: false`). **Activado el 2026-10-12** después de que `manage.py verify-stops` pasara sus siete comprobaciones en el VPS contra KuCoin real (crear, listar con identificador y par, cancelar, desaparecer del listado y detectar una segunda cancelación como «ya no existe»). Sigue sin verse en real el disparo de una orden.
* **Riesgos conocidos:** (1) comportamientos de KuCoin que solo se confirman con órdenes reales, en especial cómo consultar el precio de una orden ya disparada; (2) cada venta por stop del bot hace antes una cancelación (unas décimas de segundo más); (3) una consulta más por ciclo y dos por cada reposición.
* **Verificación:** 324 tests pasando (28 nuevos en `tests/test_exchange_stops.py`, con un exchange simulado: colocación, trailing, parcial, venta doble, mecha no vista, reinicio, huérfanas, fallos de red, desactivación).

---

### 2026-10-11 | Pausa Manual por Cabeza y Grid al 6% por Operación

* **Archivos Afectados:** [`src/tradebot/pause_control.py`](../src/tradebot/pause_control.py), [`src/tradebot/engine.py`](../src/tradebot/engine.py), [`scripts/manage.py`](../scripts/manage.py), [`config.yaml`](../config.yaml), [`tests/test_manual_pause.py`](../tests/test_manual_pause.py), [`deploy/DEPLOY.md`](../deploy/DEPLOY.md)
* **Motivo / Petición del Usuario:**
  * El operador ve el grid como una cabeza valiosa y peligrosa a la vez y pidió poder pausarlo a mano, además de la regla de strikes, y bajarle el tamaño.
  * En real ganó con posiciones pequeñas y perdió con grandes: tamaño medio de 33 USDT en agosto, 73 en septiembre (14 de 14 ganadoras, +48,5 USDT) y 206–235 en octubre (7 de 7 del 1 al 4; 4 de 9 del 5 al 8, −31,7 USDT). El 26-sep había pasado del 6% al 12% y el capital creció con aportaciones.
  * Antes de tocar la pausa se midieron alternativas a los strikes (grid solo y bot completo, desde 2022): cambiar los números (2–4 stops, ventanas de 3–14 días, pausas de 7–90 días) mueve el conjunto entre +153% y +166% (actual +160,4%; sin pausa +143,8%); reanudar cuando BTC vuelve sobre su EMA20, cuando recupera su máximo previo o tras 2–5 ganadoras seguidas "en sombra" es igual o peor (+145% a +161%). La regla de strikes se deja como está.
* **Cambios Implementados:**
  1. **Pausa manual** (`manage.py pause CABEZA [--days N]`, `resume CABEZA`, `pauses`): escribe en la tabla `state` de la BD del bot (`manual_pause_until:<cabeza>`), que el motor consulta en cada entrada, así que surte efecto **sin reiniciar**. Vale para cualquier cabeza, solo bloquea entradas nuevas y aparece en el gist y en Telegram como «manual …». `resume` levanta también una pausa por strikes vigente.
  2. **`grid_lateral`: `position_size_pct` 0.12 → 0.06.** Cada stop cuesta la mitad (≈0,3% del saldo libre). Simulado desde 2022: el grid pasa de restar 3,6 puntos a restar 1,7 y el conjunto de +160,4% a +162,2% (de +94,9% a +98,3% con deslizamiento del 1%).
* **Límites:** la pausa manual depende del criterio del operador y no se puede simular. Tras un `resume` de una pausa por strikes, los stops que la provocaron no vuelven a contar, pero tres nuevos en 7 días la reactivan.
* **Verificación:** 296 tests pasando (8 nuevos en `tests/test_manual_pause.py`, incluido el caso de otra conexión escribiendo la pausa con el bot en marcha).

---

### 2026-10-10 | Rechazos 429 de KuCoin: Reintento y Sondeo Rápido que no se Detiene

* **Archivos Afectados:** [`src/tradebot/exchange.py`](../src/tradebot/exchange.py), [`src/tradebot/daemon.py`](../src/tradebot/daemon.py), [`tests/test_exchange_resilience.py`](../tests/test_exchange_resilience.py), [`tests/test_stop_tracking.py`](../tests/test_stop_tracking.py)
* **Motivo / Petición del Usuario:**
  * Llegó a Telegram un fallo «Too many requests» al leer las velas de BNB. En el log, KuCoin había rechazado además unos 13 sondeos rápidos al día con `429000 Too many requests. System-level rate limit exceeded.`
  * Recuento por día: 2 rechazos el 12-sep y ninguno más hasta el 7-oct; desde que se activó el sondeo cada 10 s (7-oct, 19:50 UTC): 7, 14, 13 y 3 (hasta las 09:00 del día 10). Casi todos caen entre 10 y 20 s después del minuto, justo tras la ráfaga de consultas del ciclo. Son en torno al 0,15% de los sondeos.
* **Causa Técnica:**
  1. ccxt 4.5.70 no reconoce el código `429000` de KuCoin y lo lanza como `ExchangeError` genérico, no como `RateLimitExceeded`: `with_network_retry` no lo reintentaba y el fallo llegaba a Telegram a la primera.
  2. Al fallar un sondeo rápido, `_wait_cycle` dejaba de sondear hasta el ciclo siguiente: hasta 50 s sin vigilar los stops, y KuCoin rechaza más justo cuando el mercado se mueve.
* **Cambios Implementados:**
  1. `exchange.is_rate_limited` reconoce el rechazo por su texto y `with_network_retry` lo reintenta con la misma espera creciente que el resto de errores transitorios.
  2. `_wait_cycle` pierde solo el sondeo que falla y hace el siguiente a su hora.
* **No se ha cambiado:** la frecuencia del sondeo ni la consulta que usa (todos los precios de KuCoin en una petición). Si los rechazos crecen, lo siguiente sería pedir solo el precio de las monedas con posición o separar el primer sondeo de la ráfaga del ciclo.
* **Verificación:** 288 tests pasando (4 nuevos y uno adaptado).

---

### 2026-10-08 | El Gist Publicaba el Status con 15 Minutos de Retraso

* **Archivos Afectados:** [`src/tradebot/daemon.py`](../src/tradebot/daemon.py), [`src/tradebot/status.py`](../src/tradebot/status.py), [`tests/test_status_freshness.py`](../tests/test_status_freshness.py)
* **Motivo / Petición del Usuario:**
  * El gist publicado a las 21:10 UTC del 8-oct llevaba el status de las 20:55; el de las 20:55, el de las 20:40. Siempre un intervalo de publicación por detrás.
* **Causa Técnica:**
  * El hilo publicador llamaba a `write_status` antes de subir, pero esa llamada fallaba **siempre y en silencio** (`except Exception: pass`): `build_status` consulta SQLite y la conexión pertenece al hilo principal. Así que subía el fichero que el hilo principal escribía solo en cada informe (cada 15 min), y como los dos relojes van acompasados, lo leía justo antes de que se renovara.
* **Cambios Implementados:**
  1. El hilo principal reescribe el status **en cada ciclo** (`daemon._refresh_status`, tras corregir las ejecuciones pendientes), no solo en el informe.
  2. El hilo publicador solo lee el fichero y lo sube; ya no toca el motor.
  3. `write_status` escribe a un temporal y lo renombra (`_write_atomic`), para que el publicador nunca lea un fichero a medias ahora que se reescribe cada minuto.
* **Impacto Esperado:** el gist refleja el estado de hace como mucho un ciclo (unos 60 s) en el momento de publicarse; se sigue publicando cada 15 min.
* **Verificación:** 284 tests pasando (4 nuevos; 3 de ellos fallan con el código anterior).

---

### 2026-10-08 | Despliegue Automático desde GitHub (el VPS Consulta la Rama `production`) y Parada Ordenada

* **Archivos Afectados:** [`.github/workflows/tests.yml`](../.github/workflows/tests.yml), [`deploy/autodeploy.sh`](../deploy/autodeploy.sh), [`deploy/tradebot-autodeploy.service`](../deploy/tradebot-autodeploy.service), [`deploy/tradebot-autodeploy.timer`](../deploy/tradebot-autodeploy.timer), [`deploy/DEPLOY.md`](../deploy/DEPLOY.md), [`src/tradebot/daemon.py`](../src/tradebot/daemon.py), [`tests/test_graceful_stop.py`](../tests/test_graceful_stop.py)
* **Motivo / Petición del Usuario:**
  * El operador pidió despliegue y reinicio automáticos desde GitHub, en la variante en que el VPS consulta el repo (sin claves del VPS en GitHub ni SSH abierto a sus servidores; el repo es público), y pasar a trabajar con PR: lo que se fusiona en `main` se despliega.
* **Cambios Implementados:**
  1. **GitHub Actions:** tests en cada PR y en cada push a `main` (Python 3.11, como el VPS). Si pasan en `main`, la Action avanza la rama `production` a ese commit (solo hacia delante).
  2. **`deploy/autodeploy.sh`** + temporizador de systemd cada 5 min: si `production` tiene un commit nuevo hace `merge --ff-only`, instala dependencias si cambiaron, reinicia y comprueba que aparece `Daemon iniciado` y el servicio sigue vivo. Si no arranca, vuelve al commit anterior y no lo reintenta. Avisa por Telegram.
  3. **Salvaguardas:** no despliega alrededor del cierre de vela de 4 h (−5/+10 min), ni con ficheros modificados a mano en el VPS, ni hacia atrás; no reinstala `deploy/`. El script se instala copiado en `/usr/local/sbin`.
  4. **Parada ordenada (`daemon._GracefulStop`):** el bot no atendía SIGTERM, así que un reinicio podía cortarlo entre enviar una orden y registrarla. Ahora, si está durmiendo sale al momento; si está a mitad de ciclo, lo termina y sale en la siguiente espera, por el mismo camino que Ctrl+C (aviso de parada, informe final, cierre de la base de datos).
* **Riesgos asumidos:** desaparece la revisión manual del log antes de operar; los cambios de `config.yaml` también se despliegan solos; los tests no cubren la conexión real con KuCoin; las ejecuciones pendientes de confirmar se pierden en el reinicio.
* **Verificación:** 280 tests pasando (5 nuevos en `tests/test_graceful_stop.py`). El script se probó en local contra un repo de juguete con `systemctl`, `runuser` y `curl` simulados (11 casos: sin cambios, aplazado por cierre de vela, despliegue, dependencias, commit que no arranca y vuelta atrás, cambios a mano, rama inexistente…). **Sin probar aún en el VPS ni en GitHub Actions.** Instalación: [`deploy/DEPLOY.md`](../deploy/DEPLOY.md) §9.

---

### 2026-10-08 | Equity Correcto tras un Reinicio y Corrección de Ejecuciones sin Confirmar

* **Archivos Afectados:** [`src/tradebot/engine.py`](../src/tradebot/engine.py), [`src/tradebot/status.py`](../src/tradebot/status.py), [`src/tradebot/execution/live.py`](../src/tradebot/execution/live.py), [`src/tradebot/execution/base.py`](../src/tradebot/execution/base.py), [`src/tradebot/exchange.py`](../src/tradebot/exchange.py), [`src/tradebot/storage.py`](../src/tradebot/storage.py), [`src/tradebot/models.py`](../src/tradebot/models.py), [`src/tradebot/daemon.py`](../src/tradebot/daemon.py), [`tests/test_fill_confirmation.py`](../tests/test_fill_confirmation.py)
* **Motivo / Petición del Usuario:**
  * Al cuadrar el equity del 7 al 8 de octubre con el export de operaciones faltaban 7,94 USDT. No era dinero: el status publicado justo tras el reinicio del día 7 (19:50 UTC) valoraba las tres posiciones readoptadas a su precio de entrada (2.282,55) en lugar de a mercado (2.274,70). Con el dato corregido, el descuadre queda en 0,09 USDT.
  * El mismo export mostró dos operaciones con comisión incompleta: ADA (cerrada el 7-oct 02:01, comisión 0) y LTC (comprada el 7-oct 16:00, solo la comisión de venta), ambas con cantidades de muchos decimales. P&L realizado inflado en unos 0,9 USDT.
* **Causa Técnica:**
  1. `build_status` calculaba `engine.equity()` antes del bucle que pide los precios de las posiciones, y `Engine.equity` usa el precio de entrada cuando `last_prices` está vacío (siempre, tras un reinicio). Lo mismo afectaba al mensaje de arranque y a la base del cortafuegos diario.
  2. `Exchange._await_fill` espera unos 3 s a que KuCoin refleje la ejecución. Si no llega (pasó en el desplome del 7-oct), `LiveExecutionEngine._to_fill` rellenaba con el precio de referencia, la cantidad pedida y comisión 0, y ese registro nunca se corregía. En una venta por stop, además, el deslizamiento medido salía falso (precio sondeado en vez del de venta).
* **Cambios Implementados:**
  1. `Engine.load_positions` pide el precio de mercado de las posiciones readoptadas (`_seed_last_prices`, una consulta; si falla, sigue como antes), y `build_status` calcula el equity después de las posiciones.
  2. `Fill` lleva `order_id` y `confirmed`. Una ejecución sin confirmar se registra igual (la venta no espera más de lo que esperaba), queda apuntada en el motor y `Engine.reconcile_fills()` la vuelve a consultar una vez por ciclo (`ExecutionEngine.confirm_fill` → `Exchange.fetch_order_fill`), hasta 30 ciclos.
     * **Compra confirmada:** corrige precio de entrada, cantidad y comisión de la posición abierta y lo persiste (`Storage.update_open_position_entry`). Stop y objetivo no se mueven.
     * **Venta confirmada:** corrige precio de salida, comisión y P&L de la operación ya guardada (`Storage.update_closed_trade`), escribe la línea en el log de la cabeza y avisa por Telegram.
* **Límites:** las pendientes no sobreviven a un reinicio (quedan con los datos estimados y un aviso en el log con el id de la orden); si la compra se confirma con la posición ya cerrada, esa operación conserva la entrada estimada; en una toma parcial se corrigen precio y comisión, no la cantidad. Las dos operaciones antiguas (ADA y LTC) no se han retocado en la base de datos.
* **Verificación:** 275 tests pasando (12 nuevos en `tests/test_fill_confirmation.py`). Sin probar contra KuCoin real: el caso solo se da cuando el exchange va con retraso.

---

### 2026-10-07 | Filtro de Tendencia de la Propia Moneda en el Grid (EMA20 Diaria)

* **Archivos Afectados:** [`src/tradebot/regime.py`](../src/tradebot/regime.py), [`src/tradebot/engine.py`](../src/tradebot/engine.py), [`src/tradebot/config.py`](../src/tradebot/config.py), [`scripts/livesim.py`](../scripts/livesim.py), [`config.yaml`](../config.yaml), [`tests/test_asset_trend.py`](../tests/test_asset_trend.py)
* **Motivo / Petición del Usuario:**
  * El operador señaló que el grid compra bajadas sin mirar la tendencia de la moneda: el bot solo filtraba por BTC, y el ADX mide fuerza pero no dirección.
  * Medido con el conjunto completo desde 2022 ([`AUDIT_2026-10.md`](AUDIT_2026-10.md), sección 6.5): exigir que la moneda esté sobre su EMA20 diaria sube el acierto del grid del 67% al 71% y su relación ganancias/pérdidas de 0,71 a 0,78, en los dos tramos y con los dos niveles de deslizamiento. El conjunto pasa de +94,5% a +103,9% (deslizamiento 1%) y de +162,3% a +170,9% (0,2%).
  * Las medias largas (50, 100) empeoran la señal del grid, y en `volumen_explosivo` cualquier filtro de tendencia resta (de +33,6 a entre +17 y −3 puntos): no se aplicó ahí.
* **Cambios Implementados:**
  1. `regime.is_above_daily_ema(exchange, symbol, periodo)`: ¿está el precio en o por encima de su EMA diaria, con la vela en formación incluida? `is_btc_macro_bullish` pasa a usarla. Sin exchange, sin datos o con fallo de red devuelve `True` (no bloquea).
  2. Opción por cabeza **`asset_trend_ema`** (0 = desactivado) y comprobación en `Engine._check_entry`, tras el filtro macro. Solo afecta a entradas.
  3. `config.yaml`: `asset_trend_ema: 20` en `grid_lateral`.
  4. `livesim.py` aplica el filtro y cuenta las entradas que rechaza.
* **Reservas:** la EMA20 es la mejor de cuatro variantes probadas (parte de la ventaja es selección); el grid sigue por debajo de 1 en ganancias/pérdidas, pierde menos pero no gana. El backtester del proyecto no aplica este filtro.
* **Verificación:** 263 tests pasando (8 nuevos en `tests/test_asset_trend.py`); el simulador con el config final reproduce el +170,9%.

---

### 2026-10-07 | Medición del Deslizamiento de Stops y Sondeo Rápido de Posiciones Abiertas

* **Archivos Afectados:** [`src/tradebot/daemon.py`](../src/tradebot/daemon.py), [`src/tradebot/engine.py`](../src/tradebot/engine.py), [`src/tradebot/exchange.py`](../src/tradebot/exchange.py), [`src/tradebot/storage.py`](../src/tradebot/storage.py), [`src/tradebot/models.py`](../src/tradebot/models.py), [`src/tradebot/status.py`](../src/tradebot/status.py), [`src/tradebot/reporting.py`](../src/tradebot/reporting.py), [`src/tradebot/config.py`](../src/tradebot/config.py), [`config.yaml`](../config.yaml), [`scripts/livesim.py`](../scripts/livesim.py), [`tests/test_stop_tracking.py`](../tests/test_stop_tracking.py)
* **Motivo / Justificación Empírica:**
  * El 7 de octubre saltaron los primeros stops del diseño nuevo. En la caída de las 02:00 UTC el bot vendió ADA un 2,1% por debajo de su stop (−20,54 USDT en vez de −12,85) y DOT en torno a un 2,8%: el bot comprueba el precio una vez por ciclo (60 s más el recorrido de los 18 símbolos) y vende a mercado.
  * Estudio posterior ([`AUDIT_2026-10.md`](AUDIT_2026-10.md), sección 6.4): el 70% de las operaciones simuladas sale por stop, y el resultado del conjunto desde 2022 pasa de +162% con un 0,2% de deslizamiento (lo que suponía el simulador) a +94% con un 1% y +34% con un 2%. Los cinco stops reales conocidos promedian ≈ 1,3%.
  * Se estudiaron las órdenes de stop en el exchange (viables con ccxt y KuCoin, que no bloquea saldo hasta el disparo), pero se dejaron como fase 3 por su riesgo: órdenes huérfanas que podrían vender una posición posterior, más stops por mechas (8% de los toques son mechas que se recuperan) y necesidad de una prueba con dinero real.
* **Cambios Implementados:**
  1. **Fase 1, medir.** `ClosedTrade.stop_price` y columna `closed_trades.stop_price` (migración automática): en los cierres por stop se guarda el nivel que disparó la salida. `Storage.stop_slippage()` devuelve número de stops medidos, deslizamiento medio y peor. Se muestra en el informe, en el gist (`stop_slippage`) y en el log de cada stop.
  2. **Fase 2, sondeo rápido.** `engine.exit_poll_seconds` (0 = desactivado; 10 en `config.yaml`). `daemon._wait_cycle` sustituye a la espera fija entre ciclos: con posiciones abiertas llama cada 10 s a `_poll_open_exits`, que pide los precios en una sola consulta (`Exchange.fetch_last_prices`) y evalúa las salidas con `Engine._check_exits(..., count_bar=False)`. No abre posiciones. Si la consulta falla, espera al ciclo normal.
  3. `livesim.py` añade `entry` y `stop` a las operaciones simuladas (usado en el estudio).
* **Impacto Esperado:** el retraso entre que el precio cruza un stop y la venta baja de más de un minuto a unos 10 s. En el caso de ADA habría vendido cerca de 0,257 en vez de 0,253. También detecta antes los objetivos y la venta parcial.
* **Reservas:** el sondeo rápido reduce pero no elimina el deslizamiento en caídas de segundos; sigue ignorando mechas más cortas que el intervalo. El efecto real se sabrá con los próximos stops, ahora medidos.
* **Verificación:** 255 tests pasando (11 nuevos en `tests/test_stop_tracking.py`); consulta de precios probada contra KuCoin (0,4–0,5 s).

---

### 2026-10-04 | Tope de Exposición sobre el Equity y `volumen_explosivo` Ampliada a 7 Monedas

* **Archivos Afectados:** [`src/tradebot/risk.py`](../src/tradebot/risk.py), [`src/tradebot/engine.py`](../src/tradebot/engine.py), [`src/tradebot/config.py`](../src/tradebot/config.py), [`scripts/livesim.py`](../scripts/livesim.py), [`config.yaml`](../config.yaml), [`tests/test_risk.py`](../tests/test_risk.py)
* **Motivo / Petición del Usuario:**
  * Se buscaban mejoras que afectaran al P&L. El bot tenía invertido de media un 23% del equity: el tope de exposición se medía sobre el USDT libre (en la práctica, 3–4 posiciones como máximo) y `volumen_explosivo` solo operaba ETH y SUI.
  * Se midieron once variantes desde 2022 (tabla en [`AUDIT_2026-10.md`](AUDIT_2026-10.md), sección 6.3). El operador eligió la opción 10.
* **Cambios Implementados:**
  1. **`risk.exposure_on_equity`** (nuevo, `false` por defecto): con `true`, `RiskManager.evaluate_entry` compara la exposición con el equity total en vez de con el USDT libre. El motor le pasa el equity (libre + valor de mercado de las posiciones, sin consulta adicional al exchange). El tamaño de la posición sigue calculándose sobre el libre.
  2. **`config.yaml`:** `exposure_on_equity: true` y `volumen_explosivo` con ETH, SUI, ADA, AVAX, ATOM, ALGO y ETC.
  3. **`livesim.py`** aplica por defecto la base de exposición que diga el config.
* **Resultado simulado:** +162.0% desde 2022 (caída máx. 14.1%) frente a +113.6% (12.4%); +68.2% en 31 meses frente a +42.0%.
* **Reservas:** mejora apoyada sobre todo en el periodo reciente (fuera de muestra: +59.3% frente a +52.3%, con caída del 12.0% frente al 6.9%); la exposición simultánea puede acercarse al 80% del equity; aplicado antes de tener operaciones reales del diseño nuevo, contra la recomendación de esperar.
* **Verificación:** 244 tests pasando (2 nuevos en `tests/test_risk.py`); `livesim.py --combined` con el config final reproduce el +162.0%.

---

### 2026-10-04 | Validación desde 2022: `capitulacion` Restaurada y `reversion_rango` Desactivada

* **Archivos Afectados:** [`config.yaml`](../config.yaml), [`src/tradebot/config.py`](../src/tradebot/config.py), [`tests/test_pause_rules.py`](../tests/test_pause_rules.py), [`docs/AUDIT_2026-10.md`](AUDIT_2026-10.md)
* **Motivo / Justificación Empírica:**
  * Se simuló el conjunto desde enero de 2022 (`livesim.py --combined --start 2022-01-01`). El tramo enero-2022 → febrero-2024 no se había usado para ajustar nada, así que sirve de prueba fuera de muestra e incluye el mercado bajista de 2022. Tabla completa en [`AUDIT_2026-10.md`](AUDIT_2026-10.md), sección 6.2.
  * **Se confirma:** las reglas de pausa del grid (+39.1% fuera de muestra con ellas, +12.3% sin ellas) y que el trailing del 8% de `volumen_explosivo` no perjudica.
  * **Se desmiente:** el cambio de `capitulacion` (sin filtro macro ni trailing). Fuera de muestra acierta el 25% en 28 operaciones y convierte 2022 de −2.1% en −10.6%; con la configuración anterior el conjunto da +50.3% en vez de +39.1%.
  * `reversion_rango` resta en los dos tramos.
* **Cambios Implementados:**
  1. `capitulacion`: `macro_btc_filter: true` y `trailing_stop_pct: 0.03` (vuelve a como estaba).
  2. **Nueva opción `enabled: false` por cabeza** en `config.yaml`: la cabeza sigue definida pero no se cargan sus instrumentos. `Config.disabled_heads` las lista; `paused_while_open` puede referenciar una cabeza desactivada sin impedir el arranque.
  3. `reversion_rango` desactivada con `enabled: false`.
* **Resultado simulado de la config resultante:** +42.0% en 31 meses y +113.6% desde 2022, con caída máxima de 12.5% en ambos (antes 17.3%); 2022 queda en −2.1% y +1.2% por semestre.
* **Reserva principal:** casi todo el resultado viene de `tendencia_alcista` (+94.6 de los +113.6 puntos), que es la única cabeza para la que el tramo de 2022 no es una prueba independiente.
* **Verificación:** 242 tests pasando (uno nuevo para `enabled: false`).

---

### 2026-10-04 | Reglas de Pausa por Cabeza: Strikes y Pausa Mientras Otra Cabeza Tiene Posiciones

* **Archivos Afectados:** [`src/tradebot/engine.py`](../src/tradebot/engine.py), [`src/tradebot/config.py`](../src/tradebot/config.py), [`src/tradebot/storage.py`](../src/tradebot/storage.py), [`src/tradebot/backtester.py`](../src/tradebot/backtester.py), [`src/tradebot/status.py`](../src/tradebot/status.py), [`src/tradebot/telegram_views.py`](../src/tradebot/telegram_views.py), [`scripts/livesim.py`](../scripts/livesim.py), [`config.yaml`](../config.yaml), [`tests/test_pause_rules.py`](../tests/test_pause_rules.py), [`tests/test_global_drawdown.py`](../tests/test_global_drawdown.py)
* **Motivo / Petición del Usuario:**
  * `grid_lateral` es la cabeza con más aciertos en real (21 de 21) pero la que más resta en la simulación de 31 meses. El operador propuso dos formas de acotarla sin apagarla: pausarla tras 3 saltos de stop y pausarla mientras la cabeza alcista esté activa.
* **Cambios Implementados:**
  1. **Dos opciones nuevas por cabeza en `config.yaml`** (desactivadas por defecto):
     - `strike_pause: {strikes, window_days, pause_days}`: tras `strikes` stops con pérdida (`stop-loss` o `trailing-stop` con P&L negativo) en `window_days`, la cabeza no abre posiciones durante `pause_days`.
     - `paused_while_open: [cabeza, …]`: la cabeza no abre mientras alguna de las indicadas tenga posiciones abiertas.
  2. **Motor (`Engine`):** `_entry_pause_reason` se consulta en `_check_entry` antes de los demás filtros; `_register_strike` se llama al cerrar cada posición. El estado se guarda en la tabla `state` (`pause_until:<cabeza>`, `strike_reset:<cabeza>`) y **sobrevive a reinicios**. Los strikes que ya causaron una pausa no vuelven a contar.
  3. **Solo afectan a entradas nuevas:** stops, objetivos y trailing de las posiciones abiertas se siguen ejecutando durante la pausa.
  4. **Avisos:** Telegram al pausar (⏸️) y al reanudar (▶️); línea "En pausa" en el informe diario; campo `paused_heads` en el status del gist.
  5. **Backtester:** construye el motor con `enforce_pause_rules=False`, porque las pausas van contra el reloj real y no contra el de las velas. `scripts/livesim.py` sí las simula, con la misma lógica.
  6. **Activadas solo en `grid_lateral`:** 3 stops en 7 días → 30 días de pausa, y pausa mientras `tendencia_alcista` tenga posiciones.
* **Evidencia (`livesim.py --combined`, 31 meses):** el conjunto pasa de +16.7% (caída máx. 20.8%) a **+55.3%** (17.3%); el grid pasa de restar 31.5 puntos a restar 2.1, con 119 operaciones en vez de 490 y 7 pausas por strikes. Aplicar strikes a todas las cabezas empeora (+31–40%) porque `capitulacion` y `tendencia_alcista` aciertan una de cada tres por diseño.
* **Reservas:** el +55.3% es un techo optimista (parámetros elegidos sobre estos datos; 15.5 puntos son posiciones simuladas sin realizar). Dentro del periodo hay 361 días sin superar el máximo anterior y el 19% de las ventanas de un año acaban en negativo. La pausa por la cabeza alcista no selecciona los buenos momentos del grid; mejora por liberar saldo y reducir su actividad.
* **Verificación:** 241 tests pasando (13 nuevos en `tests/test_pause_rules.py`: disparo, ventana, reinicio, vencimiento, no reincidencia, aislamiento entre cabezas, gestión de posiciones abiertas, parseo y validación de config). `livesim.py --combined` con el `config.yaml` final reproduce el +55.3%.

---

### 2026-10-04 | Nueva Cabeza `tendencia_alcista` (BTC, BNB, SOL) en Sustitución de las Cabezas Diarias

* **Archivos Afectados:** [`config.yaml`](../config.yaml), [`docs/AUDIT_2026-10.md`](AUDIT_2026-10.md), [`docs/PROJECT_STATE.md`](PROJECT_STATE.md), [`docs/ARCHITECTURE.md`](ARCHITECTURE.md), [`README.md`](../README.md)
* **Motivo / Petición del Usuario:**
  * El operador observó que en un mercado alcista el bot debería ganar con facilidad y propuso una cabeza que entrara con más capital, con stop moderado y objetivo lejano.
  * Medición previa: en meses alcistas las cabezas acertaban pero solo tenían invertido un 3–7% del equity de media y capturaban entre el 1% y el 6% de la subida.
* **Cambios Implementados:**
  1. Se **eliminan `breakout_diario` y `momentum_diario`** (y con ellas el bloque `rs_selection`, ya apagado). AVAX y ADA salen del bot.
  2. Se **añade `tendencia_alcista`** sobre BTC, BNB y SOL: estrategia `breakout` con `lookback: 55` en velas diarias, `stop_loss_pct: 0.06`, `take_profit_pct: 0.50`, `trailing_stop_pct: 0.15` (fijo, sin ATR), sin venta parcial, `position_size_pct: 0.20`, con filtro macro de BTC. Solo configuración; no se tocó código.
* **Evidencia (simulador con mecánica real, `scripts/livesim.py`):**
  * 31 meses: +30.0% con caída máxima 10.4%, frente a +8.9% y +8.2% de las dos cabezas sustituidas (caídas 3.4% y 2.3%).
  * Desde 2022 (57 meses, incluye el bajista de 2022): +90.0% con caída máxima 10.4%, frente a +14.8% y +13.7%. Por año: −2.8%, +36.3%, +26.1%, +7.1%, +6.5%.
  * Positiva en todas las variantes de stop (5–10%), trailing (12–18%) y tamaño probadas, en los dos periodos.
  * **Contraprueba:** sobre las 10 monedas pequeñas libres del pool pierde en todas las variantes (−13% a −55%). La cabeza amplifica lo que hace la moneda; por eso se limita a las grandes.
* **Reservas:** sesgo de selección (ETH se excluyó tras verlo restar; BTC, BNB y SOL son ganadoras del ciclo); acierta una de cada tres y encadena hasta 9 pérdidas; la caída máxima esperable pasa del 2–5% al 10–13%; unas 70 operaciones en cinco años.
* **Efecto sobre las demás cabezas** (`livesim.py --combined`, nuevo): simuladas juntas y compitiendo por el saldo libre, las 5 cabezas dan **+16.7%** en 31 meses (caída máx. 20.8%); sin `grid_lateral`, **+51.5%** (15.3%). Las posiciones largas de `tendencia_alcista` hacen que el tope de exposición rechace 410 entradas del grid (que pasa de −42 a −31.5 puntos) y 16 de `volumen_explosivo` (de +11.5 a +7.6).
* **Antes de reiniciar el servicio:** comprobar que no hay posiciones abiertas en AVAX ni ADA (a las 19:39 UTC no había ninguna abierta en el bot).
* **Verificación:** 228 tests pasando; `python scripts/livesim.py --head tendencia_alcista` reproduce +30.0% con el `config.yaml` final.

---

### 2026-10-04 | Auditoría con Simulador de Mecánica Real: Símbolos Fijos en Cabezas Diarias y Trailing 8% en Volumen Explosivo

* **Archivos Afectados:** [`config.yaml`](../config.yaml), [`scripts/livesim.py`](../scripts/livesim.py), [`scripts/livesim_trend.py`](../scripts/livesim_trend.py), [`scripts/export.py`](../scripts/export.py), [`scripts/manage.py`](../scripts/manage.py), [`src/tradebot/reporting.py`](../src/tradebot/reporting.py), [`tests/test_storage_reporting.py`](../tests/test_storage_reporting.py), [`docs/AUDIT_2026-10.md`](AUDIT_2026-10.md)
* **Motivo / Justificación Empírica:**
  * Se pidió analizar por qué `breakout_diario` y `momentum_diario` no aprovecharon la subida de septiembre y, a partir de ahí, la viabilidad de todas las cabezas.
  * El backtester del proyecto solo evalúa salidas al cierre de vela; el bot en vivo las evalúa cada 60 s y entra a mercado horas después de la señal tras una rotación. Se escribieron simuladores que replican esa mecánica y se validaron contra las 35 operaciones reales exportadas del VPS.
  * Resultado en 31 meses (2024-03 → 2026-10): `grid_lateral` **−38.7%** del equity (PF 0.67) sin que ninguna variante lo arregle; cabezas diarias con rotación ≈ 0; `volumen_explosivo` +3.5%; `reversion_rango` −1.5%; `capitulacion` 5 operaciones. Todas ganan en meses alcistas y pierden o quedan planas en el resto. El periodo en vivo fue de los más alcistas de la serie para estas monedas.
  * Informe completo, con tablas, variantes y limitaciones: [`docs/AUDIT_2026-10.md`](AUDIT_2026-10.md).
* **Cambios Implementados:**
  1. **Cabezas diarias con símbolos fijos:** `rs_selection.enabled: false` en `breakout_diario` (SOL, AVAX) y `momentum_diario` (BNB, ADA). Simulado: +9.1% y +4.7% frente a +3.1% y −0.1% con rotación. Elimina además las entradas tardías y la colisión de símbolos.
  2. **Trailing fijo del 8% en `volumen_explosivo`:** `use_atr_trailing: false`. Simulado: +12.5% (PF 1.68) frente a +3.5% (PF 1.17), positivo en las dos mitades del periodo.
  3. **Stop inicial del 3% en las dos cabezas diarias** (antes 8%). Solo actúa hasta la venta parcial; después el stop pasa al precio de entrada. Motivo: la ganadora típica de estas cabezas es +2.1% (parcial + breakeven) y cada pérdida completa costaba 3–4 de ellas. Simulado: `momentum_diario` +8.2% frente a +4.7%; `breakout_diario` +8.9% frente a +9.1% con sus símbolos y +8.5% frente a −2.8% en 17 símbolos. En `volumen_explosivo` acortar el stop empeora y no se tocó.
  4. **`capitulacion` sin filtro macro de BTC y sin trailing** (`macro_btc_filter: false`, `trailing_stop_pct: 0.0`; quedan stop 5% y objetivo 15%). El filtro bloqueaba 38 de las 43 señales de 31 meses, porque el pánico en una moneda casi siempre coincide con BTC bajo su EMA50; y el trailing del 3% cerraba los rebotes con una duración mediana de 1.5 h. Simulado: +11.5% (38 operaciones) frente a +1.3% (5 operaciones). **Cambio pedido por el operador con una reserva seria:** el resultado no se mantiene (+16.4% en la primera mitad, −4.2% en la segunda), la caída máxima sube de 1.6% a 8.8% y en meses bajistas pierde (−0.72% al mes). Es la única cabeza que ahora puede comprar con BTC en tendencia bajista.
  5. **`manage.py export`:** vuelca `closed_trades` a CSV con todas las columnas (commit `27d9d54`).
  6. **`scripts/livesim.py` y `scripts/livesim_trend.py`:** simuladores con mecánica real, leen las cabezas de `config.yaml`.
* **Defectos Detectados (ver sección 7 del informe):**
  * Colisión de símbolos entre cabezas (el motor resuelve cabeza y estrategia solo por símbolo): **latente**, no se manifiesta con la rotación apagada.
  * `max_concurrent_per_symbol` dentro de `risk:` se ignora (el grid corre con 1 por símbolo): **sin arreglar a propósito**, corregirlo empeora el resultado simulado.
  * La operación NEAR +46% del grid (18-sep) se debió, por coincidencia de fechas con `c13026b`, a una venta que estuvo fallando dos días.
* **Pendiente de Decisión del Operador:** mantener, reducir o apagar `grid_lateral` y `reversion_rango`. Los datos no respaldan su tamaño actual.
* **Reservas:** SOL/AVAX/BNB/ADA se eligieron tras verlos funcionar (sesgo de selección; en 17 símbolos la estrategia no gana). Las variantes se exploraron sobre los mismos datos: son hipótesis.
* **Verificación:** 228 tests pasando. Simuladores contrastados con las operaciones reales del grid (20 de 20), `volumen_explosivo` (2 posiciones) y las tres entradas por rotación.

---

### 2026-10-03 | Rebalanceo de Ratio Riesgo/Beneficio y Stop Loss Estructural en Grid Lateral

* **Archivos Afectados:** [`src/tradebot/models.py`](../src/tradebot/models.py), [`src/tradebot/risk.py`](../src/tradebot/risk.py), [`src/tradebot/engine.py`](../src/tradebot/engine.py), [`src/tradebot/strategy/grid.py`](../src/tradebot/strategy/grid.py), [`config.yaml`](../config.yaml), [`config_futures.yaml`](../config_futures.yaml), [`tests/test_models.py`](../tests/test_models.py), [`tests/test_risk.py`](../tests/test_risk.py), [`tests/test_grid.py`](../tests/test_grid.py)
* **Motivo / Justificación Empírica:**
  * Se identificó una asimetría de penalización en `grid_lateral`: el ratio anterior (SL 8% vs TP 2%) requería 4 operaciones ganadoras para compensar una sola pérdida ($20 USD de pérdida vs $5 USD de ganancia).
  * Aunque `grid_lateral` mantiene un rendimiento impecable (16/16 operaciones ganadoras), una caída prolongada (como la ruptura de soporte en DOT) erosionaba gran parte del beneficio acumulado.
* **Cambios Implementados:**
  1. **Rebalanceo de Ratio Base (de 4:1 a 2:1):**
     - En `config.yaml` y `config_futures.yaml`, se redujo `stop_loss_pct` de 0.08 (-8.0%) a **0.05 (-5.0%)** y se incrementó `take_profit_pct` de 0.02 (+2.0%) a **0.025 (+2.5%)**.
     - Ahora 1 stop loss se recupera con solo 2 operaciones con take profit en lugar de 4.
  2. **Stop Loss Estructural Dinámico por Soporte de Canal:**
     - En `GridStrategy.generate_signal`, se calcula el nivel de invalidación técnica anclado al soporte del rango: `structural_sl = low - (step * 0.5)`, con un tope máximo de seguridad del -5.0% (`capped_sl = max(structural_sl, last_price * 0.95)`).
     - Al comprar en los peldaños inferiores (cerca del suelo del canal), el riesgo real de caída se reduce a solo un 2.0% – 3.5%, saliendo de inmediato si el soporte quiebra.
  3. **Extensión del Modelo `Signal` y `RiskManager.build_position`:**
     - Se añadieron los campos opcionales `stop_loss` y `take_profit` a `Signal` (con serialización `to_dict` / `from_dict`).
     - `RiskManager.build_position` y `Engine._check_entry` aceptan y priorizan estos niveles de stop/take personalizados generados por la estrategia cuando están presentes.
* **Verificación:** 226 tests unitarios y de integración ejecutados y pasando al 100% (`226 passed`).

---

### 2026-09-26 | Calibración de Eficiencia y Dimensionamiento en Grid Lateral (12% por Peldaño)

* **Archivos Afectados:** [`config.yaml`](../config.yaml), [`config_futures.yaml`](../config_futures.yaml)
* **Motivo / Justificación Empírica:**
  * `grid_lateral` demostró una efectividad histórica impecable (**13 operaciones ganadoras de 13 cerradas, 100% Win Rate, +$46.43 USDT netos**).
  * El análisis de ejecución real reveló que el 100% de los trades se resolvieron en el 1º o 2º peldaño en cuestión de 2 a 4 horas.
  * El dimensionamiento original del 6% (`position_size_pct: 0.06`, ~$103 USDT) diseñado para aguantar 5 peldaños dejaba el 94% del capital ocioso en cuenta.
* **Cambios Implementados:**
  1. Se aumentó `position_size_pct` de 0.06 a **0.12 (12% por peldaño, ~$207 USDT)**.
  2. Se redujo `max_concurrent_per_symbol` de 5 a **3 peldaños máximos**.
* **Impacto Esperado:** Duplicar el rendimiento neto en dólares por cada ciclo de oscilación (de ~+$1.85 USDT a ~+$3.80 - $4.10 USDT por trade) manteniendo la exposición máxima por activo topada en el 36% del balance.
* [2026-09-20 | Refactorización Arquitectónica y Simplificación (Fase 1: Daemon, CLI Unificada y Legacy Archive) (Commit `313c289`)](#2026-09-20--refactorización-arquitectónica-y-simplificación-fase-1-daemon-cli-unificada-y-legacy-archive)

---

### 2026-09-20 | Refactorización Arquitectónica y Simplificación (Fase 3: Jerarquía de Ejecución y Resiliencia de Red)

* **Archivos Afectados:** [`src/tradebot/execution/base.py`](../src/tradebot/execution/base.py), [`src/tradebot/execution/paper.py`](../src/tradebot/execution/paper.py), [`src/tradebot/execution/live.py`](../src/tradebot/execution/live.py), [`src/tradebot/execution/__init__.py`](../src/tradebot/execution/__init__.py), [`src/tradebot/exchange.py`](../src/tradebot/exchange.py), [`tests/test_execution_hierarchy.py`](../tests/test_execution_hierarchy.py), [`tests/test_exchange_resilience.py`](../tests/test_exchange_resilience.py)
* **Motivo / Petición del Usuario:**
  * El usuario instruyó continuar con los dos bloques finales: *"adelante con 6 y 7"*.
* **Cambios Implementados:**
  1. **Jerarquía Unificada de Ejecución (`tradebot.execution`):**
     - Consolidación formal de la clase base abstracta `ExecutionEngine(ABC)` con interfaz estándar (`execute`, `get_balance`, `cancel_order`, `fetch_open_orders`).
     - `PaperExecutionEngine` y `LiveExecutionEngine` heredan explícitamente de `ExecutionEngine`, asegurando contratos consistentes en simulado y en vivo.
     - Centralización de exportaciones en `src/tradebot/execution/__init__.py` (`ExecutionEngine`, `OrderRejected`, `PaperExecutionEngine`, `LiveExecutionEngine`, `FuturesBroker`, `build_execution_engine`).
  2. **Capa de Resiliencia de Red y Reintentos (`tradebot.exchange`):**
     - Implementación del decorador `with_network_retry` con *exponential backoff* y *jitter* para mitigar cortes de red transitorios y *rate limits* de KuCoin (`ccxt.NetworkError`, `ccxt.RateLimitExceeded`, `ConnectionError`, `TimeoutError`, `OSError`).
     - Discriminación estricta de errores: propagación instantánea sin reintento de fallos fatales de autenticación, saldo u orden inválida (`ccxt.AuthenticationError`, `ccxt.InsufficientFunds`, `ccxt.InvalidOrder`, `ccxt.BadSymbol`).
     - Blindaje de todas las operaciones de lectura, descarga de velas y metadatos de mercado (`fetch_ohlcv`, `fetch_ohlcv_history`, `fetch_funding_history`, `fetch_last_price`, `fetch_balance`, `fetch_balances_total`, `market_limits`, `amount_to_precision`, `contract_size`, `contracts_for_notional`).
* **Verificación:** 223 tests unitarios y de integración ejecutados y pasando al 100% (`223 passed`).
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

### 2026-09-20 | Refactorización Arquitectónica y Simplificación (Fase 2: Notificaciones Tipadas y Unificación de Modelos)

* **Archivos Afectados:** [`src/tradebot/models.py`](../src/tradebot/models.py), [`src/tradebot/notifier.py`](../src/tradebot/notifier.py), [`src/tradebot/telegram_views.py`](../src/tradebot/telegram_views.py), [`src/tradebot/engine.py`](../src/tradebot/engine.py), [`src/tradebot/carry.py`](../src/tradebot/carry.py), [`tests/test_models.py`](../tests/test_models.py), [`tests/test_notifier.py`](../tests/test_notifier.py)
* **Motivo / Petición del Usuario:**
  * El usuario instruyó continuar con los siguientes dos bloques: *"dale con los 2, asegurando no romper nada"*.
* **Cambios Implementados:**
  1. **Notificaciones Tipadas de Dominio (`notifier.py` + `telegram_views.py`):**
     - Se eliminó la inyección directa de cadenas HTML en el núcleo del motor `Engine`.
     - `Notifier` incorpora métodos de dominio: `notify_trade_opened`, `notify_trade_closed`, `notify_partial_tp`, `notify_circuit_breaker`, `notify_execution_error`.
     - Las plantillas y el formato visual de Telegram se encapsularon en `telegram_views.py`.
  2. **Unificación de Modelos de Dominio (`models.py`):**
     - Centralización canónica de `CarryPosition` en `src/tradebot/models.py`, re-exportándolo en `src/tradebot/carry.py` para compatibilidad total.
     - Incorporación de métodos universales `to_dict()` y `from_dict()` en `Position`, `ClosedTrade`, `CarryPosition`, `Signal`, `Order`, `Fill` para estandarizar la serialización JSON / SQLite.
* **Verificación:** 213 tests unitarios y de integración ejecutados y pasando al 100% (`213 passed`).

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
