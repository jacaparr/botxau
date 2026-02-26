"""
telegram_notify.py — Notificaciones por Telegram para el bot de trading
========================================================================
Envía alertas al móvil cuando:
  - Se abre un trade
  - Se cierra un trade (con P&L)
  - Errores del bot
  - Resumen diario

Configuración:
  1. Habla con @BotFather en Telegram → /newbot → copia el TOKEN
  2. Habla con @userinfobot → copia tu CHAT_ID
  3. Pon ambos en las variables de entorno:
       TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
       TELEGRAM_CHAT_ID=tu_chat_id
"""

import os
import json
import ssl
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Contexto SSL sin verificación (necesario en algunos VPS Windows)
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Si no hay token/chat_id, las notificaciones se desactivan silenciosamente
_ENABLED = bool(BOT_TOKEN and CHAT_ID)


# ─────────────────────────────────────────────────────────────────────────────
# ENVÍO DE MENSAJES
# ─────────────────────────────────────────────────────────────────────────────

def _send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Envía un mensaje por Telegram. Retorna True si se envió."""
    if not _ENABLED:
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        print(f"❌ Telegram API Error: {e.code} - {e.read().decode('utf-8')}")
        return False
    except (urllib.error.URLError, Exception) as e:
        print(f"❌ Connection Error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES DE NOTIFICACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def notify_trade_opened(symbol: str, signal: str, entry: float, sl: float,
                        tp: float, lot: float, risk_pct: float):
    """Notifica que se abrió un trade."""
    arrow = "📈" if signal == "LONG" else "📉"
    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)
    rr = tp_dist / sl_dist if sl_dist > 0 else 0

    text = (
        f"{arrow} <b>TRADE ABIERTO</b>\n\n"
        f"<b>Par:</b> {symbol}\n"
        f"<b>Señal:</b> {signal}\n"
        f"<b>Entrada:</b> {entry:.2f}\n"
        f"<b>SL:</b> {sl:.2f} ({sl_dist:.2f})\n"
        f"<b>TP:</b> {tp:.2f} ({tp_dist:.2f})\n"
        f"<b>R:R:</b> 1:{rr:.1f}\n"
        f"<b>Lote:</b> {lot}\n"
        f"<b>Riesgo:</b> {risk_pct}%\n"
        f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
    )
    _send_message(text)


def notify_trade_closed(symbol: str, signal: str, entry: float,
                        exit_price: float, pnl: float, pnl_pct: float = 0):
    """Notifica que se cerró un trade."""
    emoji = "✅" if pnl >= 0 else "❌"
    direction = "LONG" if signal == "LONG" else "SHORT"

    text = (
        f"{emoji} <b>TRADE CERRADO</b>\n\n"
        f"<b>Par:</b> {symbol} ({direction})\n"
        f"<b>Entrada:</b> {entry:.2f}\n"
        f"<b>Salida:</b> {exit_price:.2f}\n"
        f"<b>PnL:</b> ${pnl:+.2f}\n"
        f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
    )
    _send_message(text)


def notify_break_even(symbol: str, new_sl: float):
    """Notifica activación de break-even."""
    _send_message(f"🛡️ <b>Break-Even</b> | {symbol} | SL → {new_sl:.2f}")


def notify_trailing_stop(symbol: str, new_sl: float):
    """Notifica movimiento de trailing stop."""
    _send_message(f"📈 <b>Trailing Stop</b> | {symbol} | SL → {new_sl:.2f}")


def notify_eod_close(symbol: str, pnl: float):
    """Notifica cierre por fin de día."""
    emoji = "✅" if pnl >= 0 else "❌"
    _send_message(
        f"⏰ <b>Cierre EOD</b> | {symbol} | PnL: ${pnl:+.2f} {emoji}"
    )


def notify_error(error_msg: str):
    """Notifica un error del bot."""
    _send_message(
        f"🚨 <b>ERROR DEL BOT</b>\n\n"
        f"<code>{error_msg[:500]}</code>\n"
        f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
    )


def notify_bot_started(symbols: list, risk_pct: float):
    """Notifica que el bot arrancó."""
    syms = ", ".join(symbols)
    _send_message(
        f"🤖 <b>BOT INICIADO</b>\n\n"
        f"<b>Pares:</b> {syms}\n"
        f"<b>Riesgo:</b> {risk_pct}%\n"
        f"<b>Estrategia:</b> Asian Range Breakout v3\n"
        f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
    )


def notify_daily_summary(balance: float, equity: float,
                         trades_today: int, pnl_today: float):
    """Resumen diario del bot."""
    emoji = "📊" if pnl_today >= 0 else "📉"
    text = (
        f"{emoji} <b>RESUMEN DIARIO</b>\n\n"
        f"<b>Balance:</b> ${balance:,.2f}\n"
        f"<b>Equity:</b> ${equity:,.2f}\n"
        f"<b>Trades hoy:</b> {trades_today}\n"
        f"<b>PnL hoy:</b> ${pnl_today:+.2f}\n"
        f"\n🕐 {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}"
    )
    _send_message(text)


def notify_reconnection(attempt: int, success: bool):
    """Notifica intento de reconexión a MT5."""
    if success:
        _send_message(f"🔄 <b>Reconexión exitosa</b> a MT5 (intento #{attempt})")
    else:
        _send_message(f"⚠️ <b>Reconexión fallida</b> a MT5 (intento #{attempt})")


# ─────────────────────────────────────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if _ENABLED:
        print("Enviando mensaje de prueba...")
        ok = _send_message("🧪 <b>Test</b> — El bot de trading está conectado.")
        print(f"{'✅ Enviado' if ok else '❌ Error'}")
    else:
        print("⚠️ Telegram no configurado.")
        print("   Configura TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env")
