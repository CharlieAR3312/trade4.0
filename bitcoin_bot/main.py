from __future__ import annotations
import argparse
import logging
import random
import time
import os
from decimal import Decimal

from bitcoin_bot.config import Config
from bitcoin_bot.core.base_calculator import BaseCalculator
from bitcoin_bot.core.decision_engine import DecisionEngine
from bitcoin_bot.core.price_engine import PriceEngine
from bitcoin_bot.core.engine_state import GlobalEngineState
from bitcoin_bot.core.pnl_tracker import PnLTracker
from bitcoin_bot.storage.database import DBManager
from bitcoin_bot.notifications.telegram_bot import TelegramNotifier
from bitcoin_bot.core.state_machine import StateMachine
from bitcoin_bot.core.volatility_engine import VolatilityEngine
from bitcoin_bot.exchange.binance_client import BinanceClient
from bitcoin_bot.exchange.order_manager import OrderManager
from bitcoin_bot.exchange.validator import Validator
from bitcoin_bot.risk.bull_protection import BullProtection
from bitcoin_bot.risk.exposure_limiter import ExposureLimiter
from bitcoin_bot.risk.fee_calculator import FeeCalculator
from bitcoin_bot.simulation.paper_trading import PaperBinanceClient
from bitcoin_bot.storage.state_store import StateStore
from bitcoin_bot.storage.trade_log import TradeLog

def setup_logging() -> None:
    Config.ensure_directories()
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL if hasattr(Config, "LOG_LEVEL") else "INFO"),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.FileHandler(Config.LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
    )

def build_market_client():
    if Config.TRADING_MODE == "live":
        return BinanceClient()
    
    # Paper mode: Si hay API keys, conectamos a Binance en modo lectura
    # para leer precios, RSI y balances reales (pero sin ejecutar órdenes)
    live_reader = None
    if Config.BINANCE_API_KEY and Config.BINANCE_SECRET_KEY:
        try:
            live_reader = BinanceClient()
            logging.getLogger(__name__).info("📡 Modo PAPER LIVE: Conectado a Binance para lectura de datos reales")
        except Exception as exc:
            logging.getLogger(__name__).warning("No se pudo conectar a Binance para lectura. Usando datos offline: %s", exc)
    
    return PaperBinanceClient(live_reader=live_reader)

def build_engine(market_client):
    db_manager = DBManager(Config.DB_FILE)
    engine_state = GlobalEngineState()
    pnl_tracker = PnLTracker(db_manager)

    state_store = StateStore(db_manager)
    persisted = state_store.load()
    
    state_machine = StateMachine.from_dict(persisted.get("state_machine"))
    base_calculator = BaseCalculator.from_dict(persisted.get("base"))
    
    price_engine = PriceEngine(market_client, engine_state)
    peak = persisted.get("peak_price")
    if peak:
        price_engine.peak_price = Decimal(str(peak))
    
    volatility_engine = VolatilityEngine(market_client)
    
    # Notificador opcional
    notifier = None
    if Config.TELEGRAM_BOT_TOKEN and Config.TELEGRAM_CHAT_ID != "0":
        try:
            notifier = TelegramNotifier(
                token=Config.TELEGRAM_BOT_TOKEN,
                chat_id=Config.TELEGRAM_CHAT_ID,
                price_engine=price_engine,
                state_machine=state_machine,
                base_calculator=base_calculator,
                market_client=market_client,
                stop_callback=engine_state.stop,
                engine_state=engine_state,
                pnl_tracker=pnl_tracker
            )
            notifier.start()
        except Exception as exc:
            logging.error("No se pudo iniciar Telegram Notifier: %s", exc)
    
    engine = DecisionEngine(
        market_client=market_client,
        price_engine=price_engine,
        state_machine=state_machine,
        base_calculator=base_calculator,
        volatility_engine=volatility_engine,
        order_manager=OrderManager(market_client),
        validator=Validator(market_client),
        fee_calculator=FeeCalculator(),
        exposure_limiter=ExposureLimiter(),
        bull_protection=BullProtection(),
        trade_log=TradeLog(db_manager),
        state_store=state_store,
        notifier=notifier
    )
    return price_engine, engine, engine_state

def run_paper_demo(price_engine, engine, market_client, steps: int) -> None:
    logger = logging.getLogger(__name__)
    logger.info("Iniciando DEMO Offline (Paper Mode)...")
    for _ in range(steps):
        var = Decimal(str(random.uniform(-0.012, 0.012)))
        current = market_client.get_price(Config.SYMBOL)
        next_price = max(Decimal("1000.0"), current * (Decimal("1") + var))
        
        market_client.set_price(next_price)
        price_engine.fetch_price()
        engine.on_price_tick(price_engine)
        time.sleep(0.1)

def main() -> None:
    parser = argparse.ArgumentParser(description="Bot acumulador BTC/USDT - Remediation Audit Edition")
    parser.add_argument("--demo", action="store_true", help="Simulacion 100%% offline sin red")
    parser.add_argument("--steps", type=int, default=40, help="Ticks a usar en demo")
    args = parser.parse_args()
    
    setup_logging()
    
    # En modo demo forzamos modo paper aunque el .env diga live
    if args.demo:
        Config.TRADING_MODE = "paper"
        
    market_client = build_market_client()
    price_engine, engine, engine_state = build_engine(market_client)
    
    if args.demo:
        run_paper_demo(price_engine, engine, market_client, args.steps)
    else:
        price_engine.run_loop(engine.on_price_tick)

if __name__ == "__main__":
    main()
