# 🧠 ESTADO DEL PROYECTO Y GUÍA DE ONBOARDING (Cero Contexto)

> **Documento para Desarrolladores y Agentes de IA:**  
> Este documento contiene el contexto completo, las decisiones arquitectónicas, el historial evolutivo, la estructura del código y los resultados empíricos del proyecto **tradebot** a fecha de **Septiembre de 2026**. Cualquier desarrollador o agente que inicie una sesión sin historial previo puede comprender el 100% del sistema leyendo este archivo.

---

## 📌 1. Resumen Ejecutivo del Proyecto

*   **Objetivo:** Bot cuantitativo de trading algorítmico multicabeza, autónomo y desatendido, operando en **KuCoin Live (Dinero Real)**.
*   **Capital Operativo:** **~\$1.500 – \$1.535 USDT** (repartido entre Spot y margen de Futuros).
*   **Resultados Reales en Vivo:**
    *   **Win Rate:** **93.8%** (15 victorias de 16 operaciones cerradas).
    *   **Beneficio Realizado en Caja:** **+\$38.78 USDT**.
    *   **Beneficio Neto Global (Caja + Flotante):** **+\$50.97 USDT**.
    *   **Máximo Drawdown:** **0.0%** (Cero pérdidas catastróficas).
*   **Infraestructura:** Corre 24/7 en un servidor **VPS Linux (Ubuntu)** gestionado por `systemd` como servicio daemon permanente (`tradebot.service`).

---

## 📜 2. Historial de Evolución y Decisiones Clave de Diseño

### A) El Punto de Partida y la Eliminación del Scalping
*   Inicialmente el bot probó estrategias de alta frecuencia y scalping en 5 minutos (`scalping5m`).
*   **Conclusión empírica:** En el mercado cripto minorista, las comisiones de exchange devoran cualquier ventaja en marcos de 1m–15m.
*   **Decisión:** Se creó el script `scripts/cleanup_legacy.py` para purgar los registros antiguos de scalping y se rediseñó el sistema hacia **timeframes altos (1D y 4H)** con bajas comisiones y alto ratio beneficio/riesgo.

### B) La Arquitectura "La Hidra" (6 Cabezas Especializadas)
En lugar de forzar una única estrategia para todos los mercados, el bot despliega 6 cabezas simultáneas sobre un balance unificado:
1. **`breakout_diario` (1D):** Rupturas de Donchian 20d para capturar tendencias explosivas tempranas.
2. **`momentum_diario` (1D):** Cruces de medias EMA 10/30 con canales ATR para seguimiento institucional.
3. **`grid_lateral` (4H):** Cuadrícula dinámica de soporte/resistencia con filtro ADX < 25 (9 victorias de 9 trades).
4. **`reversion_rango` (4H):** Reversión a la media con Bandas de Bollinger y RSI en rangos consolidados.
5. **`volumen_explosivo` (4H):** Detección de acumulación de ballenas con volumen > 2.0x.
6. **`capitulacion` (4H):** Francotirador de pánicos extremos (RSI < 20) para comprar rebotes en "V".

### C) Escáner Continuo de Fuerza Relativa (RS vs BTC en 4H)
*   Las cabezas de tendencia no usan activos fijos: un evaluador programado en `daemon.py` calcula la **Fuerza Relativa contra Bitcoin a 14 días** cada 4 horas (00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC).
*   Selecciona automáticamente los **2 activos líderes** de un pool de 25 altcoins líquidas y les asigna el capital.
*   Incorpora un **filtro de histéresis del 5.0%** para evitar rotaciones excesivas por pequeñas fluctuaciones.

### D) Carry Trade Delta-Neutral (Cash & Carry)
*   Ejecuta compras en Spot y simultáneamente abre cortos 1x aislados en KuCoin Futures por el mismo importe nominal ($\Delta = 0.000$).
*   Cobra la tasa de financiación (*funding rate*) cada 8 horas (04:00, 12:00, 20:00 UTC).
*   Solo abre si el funding anualizado supera el **+10% anual** y cierra automáticamente si cae a 0% para no pagar nunca comisiones.

### E) Reglas de Oro de Gestión de Riesgo
1. **Guarda Macro Bitcoin:** Si $\text{BTC} < \text{EMA 50 Diaria}$, todas las compras se bloquean y el bot se refugia en **100% USDT líquido**.
2. **Toma Parcial 50% @ +5%:** Al llegar al +5% de ganancia, vende la mitad y asegura el dinero en caja.
3. **Stop Loss a Breakeven Inmediato:** Tras la toma parcial, el Stop Loss restante se fija en el precio de entrada (Riesgo Cero).
4. **Chandelier Trailing Stop:** Deja correr el 50% restante con un trailing stop dinámico basado en ATR.

---

## 🗂️ 3. Mapa de Archivos del Código Fuente (`src/tradebot/`)

```
src/tradebot/
├── daemon.py              # Bucle principal desatendido, scheduler 4H RS, reportes medianoche, Telegram.
├── engine.py              # Orquestador de cartera, cálculo de equity Spot+Carry, ejecución de SL/TP.
├── risk.py                # Gestión de riesgo, ATR volatility sizing, cortafuegos diario, veto macro BTC.
├── relative_strength.py   # Algoritmo de ranking RS vs BTC con histéresis anti-whipsaw.
├── carry.py               # Gestor del Carry Trade, contabilidad delta-neutral y runner en segundo plano.
├── carry_live.py          # Ejecutor real de Carry en KuCoin (compras Spot + cortos perpetuos).
├── status.py              # Ensamblador del estado unificado (Spot + Futuros + Carry).
├── publisher.py           # Publicador autónomo del status.json al secreto de GitHub Gist.
├── config.py              # Parser de config.yaml y aplanador del universo de instrumentos.
├── exchange.py            # Capa de datos de mercado y wrappers de CCXT (KuCoin).
├── models.py              # Dataclasses tipadas (Order, Fill, Position, ClosedTrade, Signal).
├── indicators.py          # Indicadores técnicos en pandas puro (EMA, ATR, RSI, ADX, Bollinger, Donchian).
├── notifier.py            # Cliente de notificaciones de Telegram con formato HTML y prefijos de modo.
│
├── execution/
│   ├── base.py            # Interfaces base y excepción OrderRejected.
│   ├── live.py            # Ejecutor Spot real en KuCoin con buffer de comisiones (0.5%).
│   ├── futures.py         # Broker de KuCoin Futures (órdenes de cortos 1x en contratos).
│   └── paper.py           # Ejecutor simulado para backtesting y paper trading.
│
└── strategy/
    ├── base.py            # Clase abstracta Strategy con generate_signal().
    ├── breakout.py        # Donchian Channel breakout.
    ├── momentum.py        # EMA + ATR Channel momentum.
    ├── grid.py            # Rejilla dinámica en rango con filtro ADX.
    ├── range_reversion.py # Bandas de Bollinger + RSI reversión.
    ├── volume_surge.py    # Explosión de volumen relativo > 2.0x.
    └── capitulation.py    # Caza de pánicos con RSI < 20.
```

---

## 📊 4. Rendimiento Empírico Auditado por Cabezas

| Cabeza / Módulo | Estrategia | Trades | Victorias | Win Rate | P&L Realizado | Estado y Rol |
|---|---|:---:|:---:|:---:|:---:|---|
| 👑 **`grid_lateral`** | Rejilla 4H | 9 | 9 | **100.0%** | **+\$11.54 USDT** | Generador de caja constante en rangos. |
| 🚀 **`breakout_diario`** | Ruptura 1D | 3 | 3 | **100.0%** | **+\$14.45 USDT** | Mayor extractor de alpha en tendencias. |
| 🔄 **`reversion_rango`** | Bollinger 4H | 1 | 1 | **100.0%** | **+\$12.90 USDT** | Cierre récord en un solo trade (`DOT`). |
| 🟢 **`momentum_diario`** | EMA/ATR 1D | 3 | 2 | **66.7%** | **-\$0.11 USDT** | En breakeven, recuperando rápido. |
| 🌊 **`volumen_explosivo`**| Volume Surge 4H| 0 | 0 | — | — | Vigilando `ETH` y `SUI`. |
| 🩸 **`capitulacion`** | Flash Crash 4H| 0 | 0 | — | — | Vigilando `DOGE`, `XRP`, `UNI`. |
| 🛡️ **`carry_trade`** | Delta-Neutral | — | — | — | **+\$0.25 USDT** | Intereses pasivos cada 8 horas. |
| **TOTAL CONSOLIDADO** | **La Hidra** | **16** | **15** | **93.8%** 🎯 | **+\$38.78 USDT** | **+50.97$ Beneficio Neto Total** |

---

## 🛠️ 5. Guía de Operación y Comandos Habituales

### Actualización en el VPS tras cambios de código:
```bash
cd ~/trade-bot
git pull origin main
sudo systemctl restart tradebot
sudo journalctl -u tradebot -f   # Para ver los logs en directo
```

### Comprobaciones y Diagnósticos:
```bash
# 1. Ejecutar toda la suite de tests (191 tests pasando)
python -m pytest

# 2. Diagnosticar en vivo el estado técnico de todas las cabezas
python scratch/diagnose_market.py

# 3. Ver informe de base de datos
python scripts/report.py
```

### Telemetría en Tiempo Real:
El bot publica su estado cada 15 minutos en un GitHub Gist privado (`tradebot_status.json`), que alimenta dashboards y herramientas de monitorización en tiempo real.
