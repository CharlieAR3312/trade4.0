from __future__ import annotations
import logging
import asyncio
import threading
import time
from datetime import datetime
from typing import Optional, Callable, Any, Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler
)
from bitcoin_bot.config import Config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, price_engine=None, state_machine=None, base_calculator=None, market_client=None, stop_callback: Optional[Callable] = None):
        self.token = token
        self.chat_id = int(chat_id)
        self.price_engine = price_engine
        self.state_machine = state_machine
        self.base_calculator = base_calculator
        self.market_client = market_client
        self.stop_callback = stop_callback
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._app: Optional[Application] = None

    def start(self) -> None:
        self._thread.start()
        time.sleep(2)
        self.send("🤖 *Bot iniciado en modo* `" + Config.TRADING_MODE + "`\nUsa /start para activar el panel.")

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._init_app())

    async def _init_app(self) -> None:
        self._app = Application.builder().token(self.token).build()
        user_filter = filters.Chat(chat_id=self.chat_id)
        self._app.add_handler(CommandHandler("start", self._cmd_start, filters=user_filter))
        self._app.add_handler(CommandHandler("status", self._cmd_status, filters=user_filter))
        self._app.add_handler(CommandHandler("logs", self._cmd_logs, filters=user_filter))
        self._app.add_handler(CommandHandler("help", self._cmd_help, filters=user_filter))
        self._app.add_handler(MessageHandler(user_filter & filters.Text(["📊 Status", "⚙️ Config", "🛑 STOP"]), self._handle_main_buttons))
        self._app.add_handler(CallbackQueryHandler(self._handle_callbacks))
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        await asyncio.Event().wait()

    def send(self, message: str, keyboard=None) -> None:
        async def _send():
            try:
                await self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
            except Exception as exc:
                logger.error("Error enviando mensaje Telegram: %s", exc)
        try:
            asyncio.run_coroutine_threadsafe(_send(), self._loop).result(timeout=10)
        except Exception as exc:
            logger.warning("Timeout enviando mensaje Telegram: %s", exc)

    @property
    def bot(self):
        if self._app:
            return self._app.bot
        from telegram import Bot
        return Bot(token=self.token)

    def _get_data(self) -> Dict[str, Any]:
        price = self.price_engine.current_price if self.price_engine else 0
        base = self.base_calculator.base_price if self.base_calculator else 0
        diff = (price - base) if (price and base) else 0
        change = (diff / base * 100) if base else 0
        snap = self.market_client.get_portfolio_snapshot(Config.SYMBOL) if self.market_client else {}
        return {"state": self.state_machine.state.value if self.state_machine else "DESCONOCIDO", "price": price or 0, "base": base or 0, "change": change, "trend_emoji": "📈" if diff >= 0 else "📉", "btc": snap.get("btc_balance", 0), "usdt": snap.get("usdt_balance", 0), "total": snap.get("total_usdt", 0), "mode": Config.TRADING_MODE}

    def _build_status_msg(self, data: Dict[str, Any], title: str = "📊 *STATUS*") -> str:
        return (f"{title} | `{datetime.now().strftime('%H:%M:%S')}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🤖 Modo: `{data['mode']}`\n"
            f"🔄 Estado: `{data['state']}`\n\n"
            f"💰 Precio: `${data['price']:,.2f}`\n"
            f"{data['trend_emoji']} Delta: `{data['change']:+.2f}%` vs Base\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"₿  BTC:  `{data['btc']:.8f}`\n"
            f"💵 USDT: `{data['usdt']:.2f}`\n"
            f"🏦 TOTAL: `${data['total']:,.2f}`")

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [["📊 Status", "⚙️ Config"], ["🛑 STOP"]]
        markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("🎮 *Panel de Control* activo.\nElige una opción:", reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

    async def _handle_main_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if "Status" in text: await self._cmd_status(update, context)
        elif "Config" in text: await self._menu_config(update)
        elif "STOP" in text: await self._menu_stop_confirm(update)

    async def _menu_config(self, update: Update):
        keyboard = [[InlineKeyboardButton("🛡️ Modo Seguro", callback_data="set_mode_safe"), InlineKeyboardButton("🚀 Modo Normal", callback_data="set_mode_normal")]]
        await update.message.reply_text("⚙️ *Opciones de trading:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    async def _menu_stop_confirm(self, update: Update):
        keyboard = [[InlineKeyboardButton("✅ SÍ, APAGAR", callback_data="confirm_stop"), InlineKeyboardButton("❌ CANCELAR", callback_data="cancel")]]
        await update.message.reply_text("⚠️ *¿Seguro que quieres apagar el bot?*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    async def _handle_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if query.data == "confirm_stop":
            await query.edit_message_text("🛑 *Bot apagado. Hasta pronto.*", parse_mode=ParseMode.MARKDOWN)
            if self.stop_callback:
                threading.Thread(target=self.stop_callback, daemon=True).start()
        elif query.data == "set_mode_safe":
            if self.state_machine: self.state_machine.enter_safe_mode("Activado desde Telegram")
            await query.edit_message_text("🛡️ *Modo Seguro activado.*", parse_mode=ParseMode.MARKDOWN)
        elif query.data == "set_mode_normal":
            from bitcoin_bot.core.state_machine import BotState
            if self.state_machine: self.state_machine.transition(BotState.NEUTRO, "Restablecido desde Telegram")
            await query.edit_message_text("🚀 *Modo Normal restablecido.*", parse_mode=ParseMode.MARKDOWN)
        elif query.data == "cancel":
            await query.delete_message()

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        data = self._get_data()
        await update.message.reply_text(self._build_status_msg(data), parse_mode=ParseMode.MARKDOWN)

    async def _cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            with open(Config.LOG_FILE, "r", encoding="utf-8") as f:
                last_logs = "".join(f.readlines()[-15:])
            await update.message.reply_text(f"📝 *Últimos logs:*\n`{last_logs}`", parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await update.message.reply_text("❌ No se encontró el archivo de logs.")

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🤖 *Comandos disponibles*\n/start — Panel de control\n/status — Estado actual\n/logs — Últimas líneas del log\n/help — Esta ayuda", parse_mode=ParseMode.MARKDOWN)

    def notify_buy(self, execution: dict, level: int) -> None:
        self.send(f"🟢 *COMPRA REALIZADA*\n━━━━━━━━━━━━━━━━━━\n📍 Nivel: `{level}`\n💰 USDT: `{execution.get('quote_amount', 0):.2f}`\n₿  BTC: `{execution.get('quantity', 0):.8f}`\n📈 Precio: `${execution.get('price', 0):,.2f}`\n💸 Fee: `{execution.get('fee_paid', 0):.4f} USDT`")

    def notify_sell(self, execution: dict) -> None:
        self.send(f"🔴 *VENTA REALIZADA*\n━━━━━━━━━━━━━━━━━━\n₿  BTC: `{execution.get('quantity', 0):.8f}`\n💵 Recibido: `{execution.get('quote_amount', 0):.2f} USDT`\n📉 Precio: `${execution.get('price', 0):,.2f}`\n💸 Fee: `{execution.get('fee_paid', 0):.4f} USDT`")

    def notify_safe_mode(self, reason: str) -> None:
        self.send(f"🚨 *MODO SEGURO ACTIVADO*\n━━━━━━━━━━━━━━━━━━\n⚠️ Razón: `{reason}`")

    def notify_heartbeat(self) -> None:
        self.send(self._build_status_msg(self._get_data(), title="💓 *HEARTBEAT*"))
