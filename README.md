# 🐉 tradebot — Bot Cuantitativo Multicabeza (KuCoin)

Sistema autónomo de trading algorítmico multicabeza para **KuCoin**, diseñado con gestión de riesgo institucional, selección dinámica por **Fuerza Relativa (RS vs BTC)** y módulo **Carry Trade delta-neutral**.

> 📌 **Guía de Onboarding (Cero Contexto):** Consulta [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md) para conocer el contexto completo, las decisiones de diseño, el mapa del código fuente y los resultados empíricos auditados.  
> 📓 **Diario de Bitácora:** Consulta [docs/LOGBOOK.md](docs/LOGBOOK.md) para ver el registro cronológico de cambios, sus motivos empíricos y explicaciones técnicas.

---

## 📖 1. ¿Cómo Funciona el Sistema?

El bot opera como un **orquestador de cartera asíncrono** sobre una cuenta compartida. En lugar de depender de una sola estrategia, divide el capital entre **6 cabezas especializadas** que explotan diferentes regímenes de mercado en paralelo:

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

## 🎯 2. Las 6 Cabezas Activas y su Especialización

| Cabeza | Estrategia | Timeframe | Indicadores Clave | Objetivo | Tamaño de Orden |
|---|---|:---:|---|---|:---:|
| 🟢 **`breakout_diario`** | Ruptura Donchian | **1D** | Canal Donchian 20d, Cierre Fuerte (>75%), Filtro Macro BTC | Captura despegues verticales | **20%** (~285$) |
| 🟢 **`momentum_diario`** | Tendencia EMA/ATR | **1D** | Cruce EMA 10/30, Canal ATR 20d, Cierre Fuerte | Seguimiento de tendencia institucional | **20%** (~285$) |
| 👑 **`grid_lateral`** | Rejilla Dinámica | **4H** | ADX < 25 (Filtro Lateral), Canales de Soporte/Resistencia | Cosechar micro-oscilaciones del +2% | **6%** (~85$) |
| 🔄 **`reversion_rango`** | Reversión a la Media | **4H** | Bandas Bollinger 20 (2.0 std), RSI < 35, ADX < 25 | Comprar en soporte extremo de rango | **15%** (~210$) |
| 🌊 **`volumen_explosivo`** | Volume Surge | **4H** | Volumen > 2.0x media 20 periodos, Vela alcista | Subirse a barridos de ballenas | **15%** (~210$) |
| 🩸 **`capitulacion`** | Flash Crash Sniper | **4H** | RSI 14 < 20 (Pánico Extremo), Velas de liquidación | Cazar rebotes en "V" de pánicos | **15%** (~210$) |

---

## 🔄 3. Selección Dinámica por Fuerza Relativa (RS vs BTC)

Para las cabezas de tendencia (`breakout` y `momentum`), el bot no opera símbolos estáticos: **escanea el mercado cada 4 Horas** (00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC):
*   **Fórmula:** $\text{RS} = \text{Retorno}(14\text{d}) - \text{Retorno}_{\text{BTC}}(14\text{d})$
*   **Pool:** 25 altcoins líquidas de KuCoin.
*   **Top 2:** Selecciona automáticamente los 2 líderes con mayor fuerza relativa.
*   **Histéresis (5.0%):** Evita rotaciones innecesarias si la diferencia de rendimiento es pequeña.

---

## 🏆 4. Resultados Reales en Vivo (Track Record Empírico)

Resultados reales auditados en dinero real (**KuCoin Live**):

| Métrica | Resultado Real |
|---|:---:|
| 🎯 **Win Rate Global** | **93.8%** (15 victorias de 16 operaciones) |
| 💵 **Beneficio Realizado en Caja (P&L)** | **+\$38.78 USDT** |
| 📈 **Beneficio Flotante en Vivo** | **+\$12.19 USDT** |
| 🚀 **Beneficio Neto Total Generado** | **+\$50.97 USDT** |
| 🛡️ **Máximo Drawdown de Cuenta** | **0.0%** (Cero pérdidas no controladas) |
| 💰 **Patrimonio Total Actual** | **~\$1.534 USDT** |

### 🥇 Ranking de Efectividad por Cabezas:
1. 👑 **`grid_lateral`:** **9 de 9 victorias (100% WR)** $\rightarrow$ **+\$11.54 USDT** *(La reina de la constancia)*.
2. 🚀 **`breakout_diario`:** **3 de 3 victorias (100% WR)** $\rightarrow$ **+\$14.45 USDT** *(La mayor generadora de alpha)*.
3. 🔄 **`reversion_rango`:** **1 de 1 victoria (100% WR)** $\rightarrow$ **+\$12.90 USDT** *(Mayor beneficio en un solo trade, DOT)*.
4. 🟢 **`momentum_diario`:** **2 de 3 victorias (66.7% WR)** $\rightarrow$ **-\$0.11 USDT** *(En breakeven, recuperando rápido)*.
5. 🛡️ **`carry_trade`:** **100% Delta-Neutral** $\rightarrow$ **+\$0.25 USDT** de funding pasivo cobrado.

---

## 🚀 5. ¿Cómo se Lanza el Bot?

### A) Requisitos Previos:
```bash
python -m pip install -r requirements.txt
```
Configura tus claves en `.env` (si operas en `live`):
```env
KUCOIN_API_KEY=tu_api_key
KUCOIN_API_SECRET=tu_api_secret
KUCOIN_API_PASSPHRASE=tu_passphrase
TELEGRAM_BOT_TOKEN=tu_token_telegram
TELEGRAM_CHAT_ID=tu_chat_id
GITHUB_TOKEN=tu_github_token_para_gist
```

### B) Modos de Ejecución:

#### 1. Modo Simulación (Paper Trading):
```bash
python scripts/run.py
```

#### 2. Modo Real (Live Trading en Local / Windows):
Configura `mode: live` en `config.yaml` y ejecuta:
```bash
python scripts/run.py
```

#### 3. Modo Desatendido 24/7 en Servidor VPS (Linux / Systemd):
En tu VPS Linux, el bot corre como un servicio daemon permanente:
```bash
# Iniciar servicio
sudo systemctl start tradebot

# Reiniciar servicio (tras hacer git pull)
sudo systemctl restart tradebot

# Ver logs en tiempo real
sudo journalctl -u tradebot -f

# Comprobar estado del servicio
sudo systemctl status tradebot
```

---

## 🛠️ 6. Comandos y Scripts Útiles

```bash
# 1. Ejecutar tests automatizados
python -m pytest

# 2. Diagnosticar estado del mercado y señales en vivo
python scratch/diagnose_market.py

# 3. Ver informe de base de datos local
python scripts/report.py

# 4. Limpiar operaciones históricas o de prueba
python scripts/cleanup_legacy.py
```

---

## 📚 7. Documentación Adicional
- 📖 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): Manual técnico institucional con fórmulas, modelos de gestión de riesgo y arquitectura detallada.
- 🚀 [deploy/DEPLOY.md](deploy/DEPLOY.md): Guía paso a paso de configuración y despliegue en servidor VPS.
