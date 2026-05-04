from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv
from decimal import Decimal

# Carga de .env (opcional para --demo)
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)

class Config:
    SYMBOL = "BTCUSDT"
    BASE_ASSET = "BTC"
    QUOTE_ASSET = "USDT"
    PRICE_INTERVAL_SECONDS = 15
    
    # Scalper Agresivo: Compra en micro-caídas o breakouts (subidas continuas)
    # Fee roundtrip = 0.2% -> umbral de venta 0.5% garantiza 0.3% neto minimo
    BASE_SELL_THRESHOLD_PCT = Decimal(os.getenv("BOT_MIN_SELL_THRESHOLD_PCT", "0.005"))  # 0.5% sobre costo
    BASE_BUY_LEVEL_1_PCT = Decimal(os.getenv("BOT_BUY_LEVEL_1_PCT", "0.006"))           # 0.6% caida desde pico
    MOMENTUM_BUY_PCT = Decimal(os.getenv("BOT_MOMENTUM_BUY_PCT", "0.010"))              # 1.0% subida continua (breakout)
    BASE_BUY_LEVEL_2_PCT = Decimal(os.getenv("BOT_BUY_LEVEL_2_PCT", "0.015"))           # 1.5% caida adicional (DCA)
    
    ATR_MULTIPLIER_SELL = Decimal("0.5")
    ATR_MULTIPLIER_BUY_1 = Decimal("0.8")
    ATR_MULTIPLIER_BUY_2 = Decimal("1.5")
    
    KLINES_INTERVAL = "15m"
    RSI_PERIOD = 14
    RSI_OVERSOLD = 55    # Filtro: solo comprar si RSI < 55 (no comprar en momentum alcista)
    RSI_OVERBOUGHT = 65  # Vender si RSI >= 65 (señal de sobrecompra)

    PROFIT_SPLIT_USDT_PCT = Decimal("0.50")

    # Risk Management
    STOP_LOSS_ATR_MULTIPLIER = Decimal(os.getenv("BOT_STOP_LOSS_ATR_MULT", "1.5"))
    RISK_PER_TRADE_PCT = Decimal(os.getenv("BOT_RISK_PER_TRADE_PCT", "0.015"))
    TRAILING_STOP_PCT = Decimal(os.getenv("BOT_TRAILING_STOP_PCT", "0.004"))  # 0.4% trailing mas agresivo

    BUY_LEVEL_1_USDT_PCT = Decimal("0.60")
    BUY_LEVEL_2_USDT_PCT = Decimal("0.40")
    MAX_SELL_PCT_PER_CYCLE = Decimal("0.15")
    BINANCE_FEE_PCT = Decimal("0.001")
    MIN_NET_GAIN_RATIO = Decimal("0.30")
    MIN_USDT_TO_OPERATE = Decimal("1.50")
    MIN_BTC_TO_SELL = Decimal("0.00001")
    
    COOLDOWN_MINUTES = 5  # 5 min entre operaciones para scalper activo
    BULL_PROTECTION_DAYS = 3
    BULL_REDUCED_BUY_PCT = Decimal("0.01")
    BULL_FORCE_BUY_DAYS = 5
    BULL_FORCE_BUY_USDT_PCT = Decimal("0.25")
    
    ORDER_MAX_RETRIES = 3
    ORDER_RETRY_BASE_SECONDS = 5
    TRADING_MODE = os.getenv("BOT_TRADING_MODE", "paper").lower()
    
    # Credenciales opcionales
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
    BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "0")
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
