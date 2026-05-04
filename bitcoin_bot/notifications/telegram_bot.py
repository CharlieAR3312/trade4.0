from __future__ import annotations
import logging
import asyncio
import threading
import time
from datetime import datetime
from decimal import Decimal
from typing import Optional, Callable, Any, Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler
)
from bitcoin_bot.config import Config

logger = logging.getLogger(__name__)

def _dec(value, default="0") -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, price_engine=None, state_machine=None, base_calculator=None, market_client=None, stop_callback: Optional[Callable] = None, engine_state=None, pnl_tracker=None):
        self.token = token
        self.chat_id = int(chat_id)
        self.authorized_user_id = Config.TELEGRAM_AUTHORIZED_USER_ID or self.chat_id
        self.price_engine = price_engine
        self.state_machine = state_machine
        self.base_calculator = base_calculator
        self.market_client = market_client
        self.stop_callback = stop_callback
        self.engine_state = engine_state
        self.pnl_tracker = pnl_tracker
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
        user_filter = filters.User(user_id=self.authorized_user_id)
        
        self._app.add_handler(CommandHandler("start", self._cmd_start, filters=user_filter))
        self._app.add_handler(CommandHandler("status", self._cmd_status, filters=user_filter))
        self._app.add_handler(CommandHandler("logs", self._cmd_logs, filters=user_filter))
        self._app.add_handler(CommandHandler("help", self._cmd_help, filters=user_filter))
        self._app.add_handler(CommandHandler("pnl", self._cmd_pnl, filters=user_filter))
        
        self._app.add_handler(MessageHandler(user_filter & filters.Text(["📊 Status", "📈 PnL", "⏸️ Pause", "▶️ Resume", "🛑 STOP"]), self._handle_main_buttons))
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
        
        # Obtenemos RSI del volatility engine si esta disponible
        rsi = 50.0
        from bitcoin_bot.core.decision_engine import DecisionEngine
        # La referencia al engine o al volatility no esta directa aquí,
        # pero recibimos price_engine, state_machine, base_calculator.
        # Mejor modificar _get_data para sacar el avg_buy_price
        
        avg_price = self.state_machine.average_buy_price if self.state_machine else 0
        
        diff = (price - avg_price) if (price and avg_price) else 0
        change = (diff / avg_price * 100) if avg_price else 0
        
        snap = self.market_client.get_portfolio_snapshot(Config.SYMBOL) if self.market_client else {}
        engine_status = self.engine_state.status.value if self.engine_state else "UNKNOWN"
        
        # Calcular Targets
        peak = self.price_engine.peak_price if self.price_engine and self.price_engine.peak_price else 0
        valley = getattr(self.price_engine, 'valley_price', None) if self.price_engine else 0
        
        next_buy_drop = float(peak) * (1 - float(Config.BASE_BUY_LEVEL_1_PCT)) if peak else 0
        next_buy_momentum = float(valley) * (1 + float(getattr(Config, 'MOMENTUM_BUY_PCT', 0.01))) if valley else 0
        next_sell = float(avg_price) * (1 + float(Config.BASE_SELL_THRESHOLD_PCT)) if avg_price else 0
        
        return {
            "state": self.state_machine.state.value if self.state_machine else "DESCONOCIDO", 
            "engine": engine_status, 
            "price": price or 0, 
            "avg_price": avg_price or 0, 
            "change": change, 
            "trend_emoji": "📈" if diff >= 0 else "📉", 
            "btc": snap.get("btc_balance", 0), 
            "usdt": snap.get("usdt_balance", 0), 
            "total": snap.get("total_usdt", 0), 
            "mode": Config.TRADING_MODE,
            "next_buy_drop": next_buy_drop,
            "next_buy_momentum": next_buy_momentum,
            "next_sell": next_sell
        }

    def _build_status_msg(self, data: Dict[str, Any], title: str = "📊 *STATUS*") -> str:
        avg_str = f"${float(data['avg_price']):,.2f}" if data['avg_price'] > 0 else "N/A"
        change_str = f"{float(data['change']):+.2f}%" if data['avg_price'] > 0 else "0.00%"
        
        targets_str = ""
        if data['state'] in ["EN_BAJADA", "NEUTRO"] or (data['state'] == "MODO_SEGURO" and data['avg_price'] == 0):
            nbd = f"${data['next_buy_drop']:,.2f}" if data['next_buy_drop'] > 0 else "N/A"
            nbm = f"${data['next_buy_momentum']:,.2f}" if data['next_buy_momentum'] > 0 else "N/A"
            targets_str = f"📉 Próxima Compra (Caída): `{nbd}`\n📈 Compra en Subida (FOMO): `{nbm}`"
        else:
            ns = f"${data['next_sell']:,.2f}" if data['next_sell'] > 0 else "N/A"
            targets_str = f"🎯 Próxima Venta Target: `{ns}`"
            
        return (f"{title} | `{datetime.now().strftime('%H:%M:%S')}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🚀 Motor: `{data['engine']}`\n"
            f"🤖 Modo: `{data['mode']}`\n"
            f"🔄 Estado: `{data['state']}`\n\n"
            f"💰 Precio Actual: `${float(data['price']):,.2f}`\n"
            f"{targets_str}\n\n"
            f"⚖️ Costo Promedio (Break Even): `{avg_str}`\n"
            f"{data['trend_emoji']} Profit Real: `{change_str}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"₿  BTC:  `{float(data['btc']):.8f}`\n"
            f"💵 USDT: `{float(data['usdt']):.2f}`\n"
            f"🏦 TOTAL: `${float(data['total']):,.2f}`")

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [["📊 Status", "📈 PnL"], ["⏸️ Pause", "▶️ Resume"], ["🛑 STOP"]]
        markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("🎮 *Panel de Control* activo.\nElige una opción:", reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

    async def _handle_main_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if "Status" in text: await self._cmd_status(update, context)
        elif "PnL" in text: await self._cmd_pnl(update, context)
        elif "Pause" in text: await self._cmd_pause(update)
        elif "Resume" in text: await self._cmd_resume(update)
        elif "STOP" in text: await self._menu_stop_confirm(update)

    async def _cmd_pause(self, update: Update):
        if self.engine_state:
            self.engine_state.pause()
            await update.message.reply_text("⏸️ *Motor Pausado.* El bot no operará.", parse_mode=ParseMode.MARKDOWN)

    async def _cmd_resume(self, update: Update):
        if self.engine_state:
            self.engine_state.resume()
        if self.state_machine:
            from bitcoin_bot.core.state_machine import BotState
            if self.state_machine.state.value == "MODO_SEGURO":
                # Recalibrar la contabilidad con los fondos actuales
                self.state_machine.baseline_btc = None
                self.state_machine.transition(BotState.NEUTRO, "Modo seguro desactivado por usuario. Recalibrando balances.")
        await update.message.reply_text("▶️ *Motor Reanudado.* Bot operando normalmente y balances sincronizados.", parse_mode=ParseMode.MARKDOWN)

    async def _menu_config(self, update: Update):
        keyboard = [[InlineKeyboardButton("🛡️ Modo Seguro", callback_data="set_mode_safe"), InlineKeyboardButton("🚀 Modo Normal", callback_data="set_mode_normal")]]
        await update.message.reply_text("⚙️ *Opciones de trading:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    async def _menu_stop_confirm(self, update: Update):
        keyboard = [[InlineKeyboardButton("✅ SÍ, APAGAR", callback_data="confirm_stop"), InlineKeyboardButton("❌ CANCELAR", callback_data="cancel")]]
        await update.message.reply_text("⚠️ *¿Seguro que quieres apagar el bot?*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    async def _handle_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        
        if query.from_user.id != self.authorized_user_id:
            await query.answer("No tienes permiso para ejecutar esta accion.", show_alert=True)
            return
            
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

    async def _cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.pnl_tracker:
            await update.message.reply_text("❌ PnL Tracker no está configurado.")
            return
        
        metrics = self.pnl_tracker.calculate_metrics()
        current_price = self.price_engine.current_price if self.price_engine else 0
        report = self.pnl_tracker.format_telegram_report(metrics, current_price)
        await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)

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
        quote = _dec(execution.get("quote_amount", 0))
        qty = _dec(execution.get("quantity", 0))
        price = _dec(execution.get("price", 0))
        fee = _dec(execution.get("fee_in_usdt", execution.get("fee_paid", 0)))
        self.send(f"🟢 *COMPRA REALIZADA*\n━━━━━━━━━━━━━━━━━━\n📍 Nivel: `{level}`\n💰 USDT: `{float(quote):.2f}`\n₿  BTC: `{float(qty):.8f}`\n📈 Precio: `${float(price):,.2f}`\n💸 Fee: `{float(fee):.4f} USDT`")

    def notify_sell(self, execution: dict) -> None:
        quote = _dec(execution.get("quote_amount", 0))
        qty = _dec(execution.get("quantity", 0))
        price = _dec(execution.get("price", 0))
        fee = _dec(execution.get("fee_in_usdt", execution.get("fee_paid", 0)))
        self.send(f"🔴 *VENTA REALIZADA*\n━━━━━━━━━━━━━━━━━━\n₿  BTC: `{float(qty):.8f}`\n💵 Recibido: `{float(quote):.2f} USDT`\n📉 Precio: `${float(price):,.2f}`\n💸 Fee: `{float(fee):.4f} USDT`")

    def notify_safe_mode(self, reason: str) -> None:
        self.send(f"🚨 *MODO SEGURO ACTIVADO*\n━━━━━━━━━━━━━━━━━━\n⚠️ Razón: `{reason}`")

    def notify_heartbeat(self) -> None:
        self.send(self._build_status_msg(self._get_data(), title="💓 *HEARTBEAT*"))
