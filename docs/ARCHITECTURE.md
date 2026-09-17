# 🐉 LA HIDRA CUANTITATIVA — Documentación Técnica y Arquitectura del Sistema

Este documento recopila la arquitectura matemática, la gestión de riesgo, los módulos de ejecución y los procedimientos operativos de **tradebot (KuCoin)**.

---

## 1. Arquitectura General del Sistema

El bot opera como un gestor de cartera autónomo y asíncrono con **6 cabezas especializadas** trabajando sobre un balance unificado:

```
                  ┌───────────────────────────────────────────────────────────┐
                  │                 ORQUESTADOR DE CARTERA (Engine)           │
                  └─────────────────────────────┬─────────────────────────────┘
                                                │
         ┌───────────────────┬──────────────────┼───────────────────┬───────────────────┐
         ▼                   ▼                  ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ Breakout Diario │ │ Momentum Diario │ │ Volumen Surge   │ │ Grid Lateral    │ │ Reversión Rango │
│  (Donchian 1D)  │ │  (EMA + ATR 1D) │ │   (Ballenas 4H) │ │ (Rejilla 4H)    │ │  (Bollinger 4H) │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                  │                   │                   │
         └───────────────────┴──────────────────┼───────────────────┴───────────────────┘
                                                │
                                                ▼
                               ┌─────────────────────────────────┐
                               │   GESTIÓN DE RIESGO (RiskManager)│
                               │   - Veto Macro BTC (EMA50)      │
                               │   - Sizing Adaptativo (ATR)     │
                               │   - Toma Parcial 50% @ +5%      │
                               │   - Stop Loss a Breakeven       │
                               │   - Chandelier Trailing Stop    │
                               │   - Disyuntor Pérdida Diaria    │
                               └────────────────┬────────────────┘
                                                │
                                                ▼
                               ┌─────────────────────────────────┐
                               │      EJECUCIÓN (KuCoin Live)    │
                               │      - Spot Market Fills        │
                               │      - Buffer de Comisiones     │
                               └────────────────┬────────────────┘
                                                │
                     ┌──────────────────────────┴──────────────────────────┐
                     ▼                                                     ▼
      ┌─────────────────────────────┐                       ┌─────────────────────────────┐
      │   CARRY TRADE DELTA-NEUTRAL │                       │    TELEMETRÍA Y STATUS      │
      │   - Spot Long + Perp Short  │                       │    - Publicador Gist JSON   │
      │   - Cobro Funding cada 8h   │                       │    - Notificador Telegram   │
      │   - Margen 1x Aislado       │                       │    - Base de Datos SQLite   │
      └─────────────────────────────┘                       └─────────────────────────────┘
```

---

## 2. Las 6 Cabezas Estratégicas

Cada cabeza está diseñada para explotar una ineficiencia o régimen específico del mercado:

| Cabeza | Estrategia | Timeframe | Indicadores Clave | Objetivo | Tamaño de Orden |
|---|---|:---:|---|---|:---:|
| 🟢 **`breakout_diario`** | Ruptura Donchian | **1D** | Canal Donchian 20d, Cierre Fuerte (>75%), Filtro Macro BTC | Captura despegues verticales tempranos | **20%** (~285$) |
| 🟢 **`momentum_diario`** | Tendencia EMA/ATR | **1D** | Cruce EMA 10/30, Canal ATR 20d, Cierre Fuerte | Seguimiento de tendencia institucional | **20%** (~285$) |
| 🌊 **`volumen_explosivo`** | Volume Surge | **4H** | Volumen > 2.0x media 20 periodos, Vela alcista | Subirse al barrido de liquidez de ballenas | **15%** (~210$) |
| 👑 **`grid_lateral`** | Rejilla Dinámica | **4H** | ADX < 25 (Mercado Lateral), Canales de Soporte/Resistencia | Cosechar micro-oscilaciones del +2% | **6%** (~85$) |
| 🔄 **`reversion_rango`** | Reversión a la Media | **4H** | Bandas Bollinger 20 (2.0 std), RSI < 35, ADX < 25 | Comprar en soporte extremo de rango | **15%** (~210$) |
| 🩸 **`capitulacion`** | Flash Crash Sniper | **4H** | RSI 14 < 20 (Pánico Extremo), Velas de capitulación | Cazar rebotes rápidos en "V" tras liquidaciones | **15%** (~210$) |

---

## 3. Selección Dinámica por Fuerza Relativa (RS vs BTC)

Para las cabezas de tendencia (`breakout` y `momentum`), el bot no opera monedas estáticas, sino que **escanea automáticamente el mercado cada 4 Horas** (00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC):

$$\text{RS}_{\text{activo}} = \text{Retorno}_{\text{activo}}(14\text{d}) - \text{Retorno}_{\text{BTC}}(14\text{d})$$

*   **Pool de Selección:** 25 altcoins líquidas de KuCoin (`SOL`, `NEAR`, `LINK`, `AVAX`, `BNB`, `DOT`, `ATOM`, `KAS`, `AR`, `UNI`, `SUI`, `ETH`, etc.).
*   **Top K:** Selecciona los **2 líderes absolutos** con mayor alpha frente a Bitcoin.
*   **Filtro de Histéresis (5.0%):** Evita rotaciones impulsivas si la diferencia de rendimiento con los líderes actuales es marginal.

---

## 4. Gestión de Riesgo y Protección de Beneficios

1. **Guarda Macro Bitcoin:**
   - Si $\text{BTC/USDT} < \text{EMA 50 Diaria}$, todas las compras direccionales se bloquean preventivamente y la cuenta se refugia en **100% USDT líquido**.
2. **Toma Parcial de Beneficios (50% @ +5.0%):**
   - Cuando una posición alcanza el **+5% de ganancia**, el bot vende automáticamente el 50% de la posición para asegurar beneficio líquido en caja.
3. **Stop Loss Automático a Breakeven:**
   - Inmediatamente tras la toma parcial, el Stop Loss del 50% restante se mueve al **precio de entrada (Breakeven)**, convirtiendo la operación en **riesgo cero**.
4. **Chandelier Trailing Stop:**
   - El 50% restante cabalga la tendencia con un trailing stop dinámico basado en ATR ($3 \times \text{ATR}$ o 10%) para maximizar ganancias.
5. **Cortafuegos de Pérdida Diaria:**
   - Si el drawdown intradía supera el límite configurado (`max_daily_loss_pct`), el bot pausa la apertura de nuevas posiciones hasta las 00:00 UTC.

---

## 5. Módulo Carry Trade (Cash & Carry Delta-Neutral)

*   **Pata Spot:** Compra $X$ USDT del activo base en mercado Spot.
*   **Pata Futuros:** Vende $X$ USDT del contrato perpetuo inverso/lineal en Futuros con **apalancamiento 1x aislado**.
*   **Delta:** $\Delta = 0.000$ (Inmune a subidas o desplomes de mercado).
*   **Cobro de Funding:** Cobra la tasa de financiación de KuCoin cada 8 horas (04:00, 12:00, 20:00 UTC).
*   **Filtros Inteligentes:**
    - Entrada solo si el funding anualizado supera el **+10% anual** (`min_annualized_pct: 10.0`).
    - Salida automática si el funding cae a **0% o negativo** (`exit_annualized_pct: 0.0`) para no pagar comisiones.

---

## 6. Persistencia y Telemetría

*   **Base de Datos SQLite (`data/tradebot.db`):** Tablas `fills`, `closed_trades`, `open_positions` y estados clave (`ath_equity`).
*   **Publicador Gist JSON (`tradebot_status.json`):** Actualización cada 15 minutos en GitHub Gist con métricas de equity unificado, posiciones vivas, precios en tiempo real y desglose por cabezas.
*   **Notificador Telegram:** Notificaciones instantáneas de aperturas, tomas parciales, cierres, cobros de funding, informe diario de medianoche (00:00 UTC) y latido de vida cada 6 horas.
