from __future__ import annotations
import os
from pathlib import Path

class Config:
    SYMBOL = "BTCUSDT"
    BASE_ASSET = "BTC"
    QUOTE_ASSET = "USDT"
    PRICE_INTERVAL_SECONDS = 15
    
    # Configuracion de Volatilidad (ATR y RSI)
    BASE_SELL_THRESHOLD_PCT = float(os.getenv("BOT_MIN_SELL_THRESHOLD_PCT", "0.015")) # 1.5% base
    BASE_BUY_LEVEL_1_PCT = float(os.getenv("BOT_BUY_LEVEL_1_PCT", "0.020")) # 2.0% base
    BASE_BUY_LEVEL_2_PCT = float(os.getenv("BOT_BUY_LEVEL_2_PCT", "0.040")) # 4.0% base
    
    ATR_MULTIPLIER_SELL = 0.5    # Vender al 50% del ATR
    ATR_MULTIPLIER_BUY_1 = 0.8   # Comprar nivel 1 al 80% del ATR
    ATR_MULTIPLIER_BUY_2 = 1.5   # Comprar nivel 2 al 150% del ATR
    
    KLINES_INTERVAL = "15m"
    RSI_PERIOD = 14
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70

    PROFIT_SPLIT_USDT_PCT = 0.50 # 50% USDT, 50% BTC

    TRAILING_STOP_PCT = float(os.getenv("BOT_TRAILING_STOP_PCT", "0.005")) # 0.5%
    BUY_LEVEL_1_USDT_PCT = 0.60
    BUY_LEVEL_2_USDT_PCT = 0.40
    MAX_SELL_PCT_PER_CYCLE = 0.15
    BINANCE_FEE_PCT = 0.001
    MIN_NET_GAIN_RATIO = 0.30
    MIN_USDT_TO_OPERATE = 1.50
    MIN_BTC_TO_SELL = 0.00001
    COOLDOWN_MINUTES = 10
    BULL_PROTECTION_DAYS = 3
    BULL_REDUCED_BUY_PCT = 0.01
    BULL_FORCE_BUY_DAYS = 5
    BULL_FORCE_BUY_USDT_PCT = 0.25
    ORDER_MAX_RETRIES = 3
    ORDER_RETRY_BASE_SECONDS = 5
    TRADING_MODE = os.getenv("BOT_TRADING_MODE", "paper").lower()
    TELEGRAM_AUTHORIZED_USER_ID = int(os.getenv("TELEGRAM_AUTHORIZED_USER_ID", "0"))
    ROOT_DIR = Path(__file__).resolve().parent.parent
    LOG_DIR = ROOT_DIR / "logs"
    DATA_DIR = ROOT_DIR / "data"
    LOG_FILE = str(LOG_DIR / "bot.log")
    TRADE_LOG_FILE = str(LOG_DIR / "trades.csv")
    STATE_FILE = str(DATA_DIR / "state.json")
    DB_FILE = str(DATA_DIR / "bot_database.sqlite")

    @classmethod
    def ensure_directories(cls) -> None:
        cls.LOG_DIR.mkdir(parents=True, exist_ok=True)
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
