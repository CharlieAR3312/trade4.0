from __future__ import annotations
import argparse
import logging
import random
import time
from bitcoin_bot.config import Config
from bitcoin_bot.core.base_calculator import BaseCalculator
from bitcoin_bot.core.decision_engine import DecisionEngine
from bitcoin_bot.core.price_engine import PriceEngine
import os
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
    return PaperBinanceClient()

def build_engine(market_client):
    db_manager = DBManager(Config.DB_FILE)
    engine_state = GlobalEngineState()
    pnl_tracker = PnLTracker(db_manager)

    state_store = StateStore(db_manager)
    persisted = state_store.load()
    state_machine = StateMachine.from_dict(persisted.get("state_machine"))
    base_calculator = BaseCalculator.from_dict(persisted.get("base"))
    price_engine = PriceEngine(market_client, engine_state)
    price_engine.peak_price = persisted.get("peak_price")
    
    volatility_engine = VolatilityEngine(market_client)
    
    # Inicializar Telegram Notifier
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    notifier = None
    if token and chat_id:
        notifier = TelegramNotifier(
            token=token,
            chat_id=chat_id,
            price_engine=price_engine,
            state_machine=state_machine,
            base_calculator=base_calculator,
            market_client=market_client,
            stop_callback=engine_state.stop,
            engine_state=engine_state,
            pnl_tracker=pnl_tracker
        )
        notifier.start()
    
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
    for _ in range(steps):
        delta = random.uniform(-0.012, 0.012)
        next_price = max(1000.0, market_client.get_price(Config.SYMBOL) * (1 + delta))
        market_client.set_price(next_price)
        price_engine.fetch_price()
        engine.on_price_tick(price_engine)
        time.sleep(0.1)

def main() -> None:
    parser = argparse.ArgumentParser(description="Bot acumulador BTC/USDT")
    parser.add_argument("--demo", action="store_true", help="Simulacion corta en modo paper")
    parser.add_argument("--steps", type=int, default=40, help="Ticks a usar en demo")
    args = parser.parse_args()
    setup_logging()
    market_client = build_market_client()
    price_engine, engine, engine_state = build_engine(market_client)
    if args.demo:
        run_paper_demo(price_engine, engine, market_client, args.steps)
    else:
        price_engine.run_loop(engine.on_price_tick)

if __name__ == "__main__":
    main()
