from __future__ import annotations
import os
from pathlib import Path

class Config:
    SYMBOL = "BTCUSDT"
    BASE_ASSET = "BTC"
    QUOTE_ASSET = "USDT"
    PRICE_INTERVAL_SECONDS = 15
    MIN_SELL_THRESHOLD_PCT = float(os.getenv("BOT_MIN_SELL_THRESHOLD_PCT", "0.0035"))
    TRAILING_STOP_PCT = float(os.getenv("BOT_TRAILING_STOP_PCT", "0.0025"))
    BUY_LEVEL_1_PCT = float(os.getenv("BOT_BUY_LEVEL_1_PCT", "0.0040"))
    BUY_LEVEL_2_PCT = float(os.getenv("BOT_BUY_LEVEL_2_PCT", "0.0070"))
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
    ROOT_DIR = Path(__file__).resolve().parent.parent
    LOG_DIR = ROOT_DIR / "logs"
    DATA_DIR = ROOT_DIR / "data"
    LOG_FILE = str(LOG_DIR / "bot.log")
    TRADE_LOG_FILE = str(LOG_DIR / "trades.csv")
    STATE_FILE = str(DATA_DIR / "state.json")

    @classmethod
    def ensure_directories(cls) -> None:
        cls.LOG_DIR.mkdir(parents=True, exist_ok=True)
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
