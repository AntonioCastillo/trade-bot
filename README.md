# tradebot — Bot de trading de criptomonedas (KuCoin)

Bot **multi-símbolo** de trading para KuCoin, orientado a **simular a lo ancho,
persistir cada operación con su P&L y comprobar viabilidad** antes de arriesgar
capital. Arranca en **modo paper (simulación)** por defecto.

> ⚠️ **Aviso.** Esto es una herramienta de software, no consejo de inversión.
> El trading con criptomonedas conlleva riesgo de pérdida total del capital.
> Valida cualquier estrategia con backtesting y paper trading antes de operar
> con dinero real, y hazlo bajo tu propia responsabilidad.

## Qué hace ("la hidra": multi-cabeza)

- Opera un **universo por cabezas**: cada cabeza = una estrategia + su **timeframe**
  + sus símbolos + su riesgo. Corren todas a la vez.
- Estrategias incluidas (registro por nombre en `strategy/`):
  - **mean_reversion** (RSI + Bollinger) — reversión, **solo-largos**.
  - **momentum** (EMA + breakout de canal + ATR/tendencia/volumen), solo-largos.
  - **volume_surge** (explosión de volumen + vela alcista), agresiva.
  - **grid** (rejilla en rango, varios peldaños) — para mercados laterales.
  - **scalping** (cruce EMA rápido) — entradas/salidas rápidas.
  - **breakout** (ruptura Donchian) — momentum-continuación.
  - **trend** (golden cross de medias) — seguimiento de tendencia en marco alto.
- **Filtro de régimen** (`regimes:` por cabeza): activar cada estrategia solo en
  su régimen (lateral / tendencia / volátil) vía ADX + ATR.
- **Sniper de recién listadas** (experimental) — corre en el mismo proceso.
- **Notificaciones por Telegram**: inicio/parada, cada operación (con **cabeza** y
  **saldo**), señal de vida 6h, fallos. Marca **🧪 [SIMULACIÓN]** o **🔴 [REAL]**.
- **Log por cabeza** en `logs/heads/`, además del log global.
- Simulación **realista**: comisiones + slippage + **mark-to-market** de posiciones
  abiertas (para no engañarse con estrategias que dejan perdedoras abiertas).
- **Persiste cada round-trip** con P&L → tabla `closed_trades`. Informe con
  métricas de robustez (profit factor, drawdown, Sharpe).

## Arquitectura

```
Market Data ──► Strategy ──► Risk Manager ──► Execution
  (ccxt)       (por símbolo)  (veto/tamaño)    (paper/live)
                                   │
        Engine (cartera) orquesta ─┘   Storage (SQLite) ──► Reporting
```

| Módulo | Responsabilidad |
|---|---|
| `config.py` | Aplana el `universe` en instrumentos (símbolo + estrategia + tf + riesgo). |
| `exchange.py` | Datos de mercado, órdenes reales y funding vía ccxt (KuCoin spot/futuros). |
| `strategy/` | 7 estrategias que emiten BUY/HOLD (solo-largos). |
| `regime.py` | Clasifica el mercado (lateral/tendencia/volátil) con ADX + ATR. |
| `risk.py` | Dimensiona por instrumento, SL/TP/trailing, pérdida diaria. **Veta.** |
| `execution/` | `paper` (comisión + slippage) o `live` (real, con fetch de fill). |
| `engine.py` | Cartera multi-cabeza; registra cada operación; equity mark-to-market. |
| `daemon.py` | Runner autónomo: bucle resiliente, reset diario, informes, notifs, sniper. |
| `notifier.py` | Notificaciones Telegram con prefijo de modo (SIMULACIÓN/REAL). |
| `sniper.py` | Detector + entrada en recién listadas (experimental). |
| `storage.py` | SQLite: `fills` + `closed_trades`. |
| `reporting.py` / `metrics.py` | Informe + robustez (PF, drawdown, Sharpe). |
| `backtester.py` | Backtest reutilizable (con mark-to-market de lo abierto). |
| `walkforward.py` | Validación walk-forward / out-of-sample (anti-sobreajuste). |
| `edge.py` | Edge-scanner: mide la ventaja bruta de una señal vs coste. |
| `pairs.py` / `funding.py` | Análisis de pairs trading y de funding-rate carry. |
| `selfcheck.py` | Verificación de la API real con una operación de ~1 USD. |

## Instalación

```bash
python -m pip install -r requirements.txt
```

No hacen falta claves de API para simular: los datos de mercado de KuCoin son
públicos. Las claves solo se usan en modo `live` (órdenes reales).

**Notificaciones por Telegram (opcional):** pon `TELEGRAM_BOT_TOKEN` y
`TELEGRAM_CHAT_ID` en `.env`. Si están, el bot avisa por Telegram en cada
apertura y cierre. Si no, no pasa nada (todo queda en el log igualmente).

**Sniper de recién listadas (experimental, alto riesgo):** activar con
`sniper.enabled: true` en `config.yaml` y lanzar aparte con
`python scripts/sniper.py`. Detecta nuevos pares */USDT y entra buscando el pump
inicial. NO es validable con backtesting; úsalo solo con capital que puedas
perder por completo.

## Uso

**1) Backtest de todo el universo** (viabilidad rápida sobre histórico):

```bash
python scripts/backtest.py          # 1000 velas/símbolo desde KuCoin
python scripts/backtest.py 500      # nº de velas por símbolo
```

Persiste en `data/backtest.db` e imprime el informe al terminar.

**2) Bot autónomo y desatendido (paper trading en tiempo real):**

```bash
python scripts/run.py               # mode: paper (por defecto)
```

Un único comando que corre en bucle sin intervención: recorre el universo,
persiste cada operación, **reinicia el cortafuegos de pérdida diaria cada día
UTC**, **nunca muere por un error puntual** y **vuelca un informe** a
`data/report.txt` cada `report_interval_seconds`. Registra todo en
`logs/tradebot.log`. Se detiene con `Ctrl+C`. Persiste en `data/tradebot.db`.

Para dejarlo corriendo **con reinicio automático** ante una caída dura del
proceso (Windows):

```bash
run_forever.bat
```

Para que arranque solo al encender el PC, programa `run_forever.bat` en el
**Programador de tareas de Windows** (disparador: "Al iniciar sesión").

**3) Validación walk-forward (¿son fiables los parámetros o es sobreajuste?):**

```bash
python scripts/walkforward.py              # 2000 velas/símbolo, con grid search
python scripts/walkforward.py 3000 nogrid  # más histórico, sin optimizar
```

Entrena los parámetros sobre tramos in-sample y los prueba en tramos
out-of-sample que nunca vio. Si el rendimiento OOS se derrumba frente al IS, los
parámetros están **sobreajustados** y no son fiables para operar en real.

**4) Consultar resultados en cualquier momento:**

```bash
python scripts/report.py data/backtest.db
python scripts/report.py                 # usa la BD de config.yaml
```

El informe incluye métricas de robustez: **profit factor**, **max drawdown** y
**Sharpe** (por operación), además del P&L por operación, símbolo y categoría.

**5) Herramientas de investigación (medir antes de arriesgar):**

```bash
python scripts/edge_scan.py 4h 3000     # ventaja bruta de cada señal vs coste
python scripts/funding_scan.py          # funding-rate carry por perpetuo
python scripts/funding_sim.py           # simula el carry delta-neutral (paper)
python scripts/verify_api.py            # verifica la API real con ~1 USD (round-trip)
```

**Tests:**

```bash
python -m pytest
```

## Configuración

Todo en `config.yaml`: el `universe` (símbolos, estrategia y overrides de riesgo
por categoría) y el bloque `risk`/`engine` globales. Los secretos, en `.env`.

Para pasar a real: `mode: live` + claves de KuCoin en `.env`. El bot pedirá
confirmación explícita por consola antes de operar con dinero.

## Consultar la base de datos directamente

Cada operación queda en SQLite; puedes hacer tus propias consultas:

```bash
sqlite3 data/backtest.db "SELECT symbol, pnl_abs, pnl_pct, exit_reason FROM closed_trades ORDER BY pnl_abs;"
```

## Hallazgos de la investigación (honesto)

Resumen de lo medido con walk-forward (out-of-sample, comisiones reales,
mark-to-market). **La conclusión transversal: el (poco) edge vive en timeframe
ALTO + holds largos + baja frecuencia; todo lo intradía/scalping pierde por
comisiones.**

| Enfoque | Veredicto |
|---|---|
| **trend-following @1d** (golden cross) | 🟢 Lo mejor: OOS **positivo** en BTC/ETH/XRP (PF>1), aunque muestras finas. |
| **reversión @4h** (RSI<25 sobreventa profunda) | 🟡 Marginal: DOGE OOS +1.9%, resto breakeven. |
| **funding-rate carry** (delta-neutral) | 🟡 Edge real pero **fino** (~3-9% anual en mercado quieto) y muy sensible a la ejecución del hedge; necesita futuros. Mejor en fase alcista. |
| momentum / breakout @1h-4h | ❌ Sobreajuste: buen IS, OOS negativo. |
| volume_surge, scalping, grid @5m-15m | ❌ Sin edge / pierden por comisiones. Grid además tiene cola catastrófica (−72%). |
| pairs ETH/BTC | ❌ El spread no cubre 2 comisiones y necesita futuros. |
| señales sueltas (vela verde, sesión horaria, squeeze) | ❌ Sin ventaja bruta sobre el coste (medido con `edge_scan`). |

**Lección de método:** medir la ventaja BRUTA de una señal (`edge_scan.py`) antes
de construir; validar SIEMPRE con walk-forward + mark-to-market (contar también
las posiciones abiertas, o una estrategia que deja perdedoras abiertas parece
rentable cuando no lo es).

## De paper a live: checklist de seguridad

1. Backtest con resultados consistentes en varios periodos y símbolos.
2. Semanas de paper trading que confirmen el comportamiento.
3. Claves de API de KuCoin **sin permiso de retirada** (solo trading).
4. Empieza con capital pequeño y `position_size_pct` bajo.
5. Vigila el `max_daily_loss_pct` — es tu cortafuegos.

## Próximos pasos sugeridos

- **Funding-rate carry en fase alcista** (cuando el funding sea alto) — el edge
  real más prometedor; requiere ejecutor de futuros + gestión de margen.
- **Afinar trend@1d** con más histórico/símbolos para firmar la muestra.
- Salida por **tiempo** (`max_hold_bars`) por cabeza en el bucle live (ya está en
  el motor/backtester; falta exponerla en `config.yaml`).
- Señales **on-chain / de flujos** (datos que el retail explota poco).
- Cartera con **capital compartido real** y presupuesto de riesgo por cabeza.
```
