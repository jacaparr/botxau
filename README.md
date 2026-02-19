# 🤖 Binance Futures Bot — EMA + RSI + ADX

Bot de trading automatizado para **Binance Futures Testnet** con estrategia EMA 9/20 + RSI 14 + ADX 14.

**Pares:** BTCUSDT · ETHUSDT · XAUUSDT · SOLUSDT | **Timeframe:** 1h

---

## 🚀 Setup Rápido

### 1. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 2. Obtener API Keys del Testnet

1. Ve a [testnet.binancefuture.com](https://testnet.binancefuture.com)
2. Inicia sesión con GitHub
3. Ve a **Account → API Key Management**
4. Crea un nuevo par de claves
5. Copia la API Key y Secret Key

### 3. Configurar credenciales
```bash
# Copia el archivo de ejemplo
copy .env.example .env

# Edita .env con tus claves reales
BINANCE_TESTNET_API_KEY=tu_api_key_aqui
BINANCE_TESTNET_SECRET_KEY=tu_secret_key_aqui
USE_TESTNET=True
```

---

## 📊 Ejecutar Backtest

```bash
# Backtest de todos los pares (1h, últimas 1000 velas ~41 días)
python backtest.py

# Backtest de un par específico
python backtest.py --symbol BTCUSDT
python backtest.py --symbol XAUUSDT

# Backtest en 4h con capital inicial de 5000 USDT
python backtest.py --interval 4h --capital 5000
```

**Salida esperada:**
```
╭──────────┬────────┬──────────┬───────────┬───────────────┬────────┬──────────────╮
│ Par      │ Trades │ Win Rate │ PnL Total │ Profit Factor │ Max DD │ Capital Final│
├──────────┼────────┼──────────┼───────────┼───────────────┼────────┼──────────────┤
│ BTCUSDT  │   23   │  52.2%   │  +$842.10 │     1.87      │ -8.3%  │  $10,842.10  │
│ ETHUSDT  │   19   │  47.4%   │  +$312.50 │     1.42      │ -11.2% │  $10,312.50  │
│ XAUUSDT  │   17   │  58.8%   │  +$621.30 │     2.14      │ -6.1%  │  $10,621.30  │
│ SOLUSDT  │   21   │  42.9%   │  -$180.20 │     0.89      │ -14.5% │   $9,819.80  │
╰──────────┴────────┴──────────┴───────────┴───────────────┴────────┴──────────────╯
```

---

## 🤖 Ejecutar el Bot

```bash
# Modo DRY-RUN: calcula señales pero NO coloca órdenes (para probar)
python bot.py --dry-run

# Modo LIVE en Testnet (coloca órdenes reales en el Testnet)
python bot.py
```

---

## 🧪 Verificar Conexión

```bash
# Verifica conexión y muestra balance del Testnet
python exchange.py

# Test de indicadores con datos sintéticos
python indicators.py
```

---

## ⚙️ Configuración de la Estrategia

Edita `config.py` para ajustar los parámetros:

| Parámetro | Default | XAUUSDT | Descripción |
|---|---|---|---|
| `ema_fast` | 9 | 9 | EMA rápida |
| `ema_slow` | 20 | 20 | EMA lenta |
| `rsi_period` | 14 | 14 | Periodo RSI |
| `rsi_long` | 55 | 55 | RSI mínimo para Long |
| `rsi_short` | 45 | 45 | RSI máximo para Short |
| `adx_min` | 25 | **20** | ADX mínimo (tendencia) |
| `atr_sl` | 1.5 | **2.0** | Multiplicador SL |
| `atr_tp` | 3.0 | **4.0** | Multiplicador TP |
| `leverage` | 3x | 3x | Apalancamiento |

---

## 📁 Estructura del Proyecto

```
futures-bot/
├── config.py        ← Parámetros y API keys
├── indicators.py    ← EMA, RSI, ADX, ATR
├── strategy.py      ← Lógica de señales
├── risk_manager.py  ← SL/TP y sizing
├── exchange.py      ← API Binance Futures
├── bot.py           ← Loop principal
├── backtest.py      ← Motor de backtesting
├── logger.py        ← Logs + CSV
├── .env             ← Tus API keys (NO subir a Git)
├── .env.example     ← Plantilla
└── requirements.txt
```

---

## ⚠️ Advertencias

> **SIEMPRE** usa `USE_TESTNET=True` hasta tener al menos 4 semanas de resultados positivos en paper trading.

> El apalancamiento amplifica pérdidas. Nunca uses más de **5x** en producción.

> Los resultados del backtest no garantizan rentabilidad futura.
