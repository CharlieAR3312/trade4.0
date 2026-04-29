from __future__ import annotations
import logging
import time
import uuid
from bitcoin_bot.config import Config
from bitcoin_bot.core.models import OrderExecution
from bitcoin_bot.exchange.binance_client import BinanceClient

logger = logging.getLogger(__name__)

class PaperBinanceClient:
    def __init__(self):
        # We wrap the real client to fetch real market data and real initial balances
        self.real_client = BinanceClient()
        
        logger.info("Conectando a Binance para obtener balances reales iniciales para Paper Trading...")
        # Get real portfolio to seed the simulator
        try:
            snapshot = self.real_client.get_portfolio_snapshot(Config.SYMBOL)
        except Exception as exc:
            logger.error("Fallo al conectar a Binance en Paper Mode. Usando defaults. Error: %s", exc)
            snapshot = None
            
        if snapshot:
            self.balances = {"BTC": snapshot["btc_balance"], "USDT": snapshot["usdt_balance"]}
            logger.info("Balances cargados desde Binance: %.8f BTC, %.2f USDT", self.balances["BTC"], self.balances["USDT"])
        else:
            self.balances = {"BTC": 0.01, "USDT": 1000.0}
            logger.warning("Usando balances por defecto debido a error de conexion.")
            
        self.current_price = self.real_client.get_price(Config.SYMBOL)
        self.symbol_info = self.real_client.get_symbol_info(Config.SYMBOL)

    def reconnect(self) -> None:
        self.real_client.reconnect()

    def get_price(self, symbol: str) -> float:
        self.current_price = self.real_client.get_price(symbol)
        return self.current_price

    def set_price(self, price: float) -> None:
        # Used strictly for fast-forward testing (e.g. --demo flag)
        self.current_price = price

    def get_balance(self, asset: str) -> float:
        return self.balances.get(asset, 0.0)

    def get_portfolio_snapshot(self, symbol: str) -> dict:
        btc_value_usdt = self.balances["BTC"] * self.current_price
        return {
            "btc_balance": self.balances["BTC"], 
            "usdt_balance": self.balances["USDT"], 
            "btc_price": self.current_price, 
            "btc_value_usdt": btc_value_usdt, 
            "total_usdt": btc_value_usdt + self.balances["USDT"], 
            "timestamp": time.time()
        }

    def get_symbol_info(self, symbol: str) -> dict:
        return self.real_client.get_symbol_info(symbol)

    def get_klines(self, symbol: str, interval: str, limit: int = 14) -> list:
        # Fetch real klines from Binance for RSI/ATR calculation
        return self.real_client.get_klines(symbol, interval, limit)

    def get_order_status(self, symbol: str, client_order_id: str) -> OrderExecution | None:
        return None

    def create_market_buy(self, symbol: str, quote_amount: float, client_order_id: str = "") -> OrderExecution:
        # We use the freshest price for the execution
        exec_price = self.get_price(symbol)
        
        if quote_amount > self.balances["USDT"]:
            raise RuntimeError("USDT insuficiente en paper trading")
            
        fee_paid = quote_amount * Config.BINANCE_FEE_PCT
        quantity = (quote_amount - fee_paid) / exec_price
        
        self.balances["USDT"] -= quote_amount
        self.balances["BTC"] += quantity
        logger.info("Paper BUY %.2f USDT -> %.8f BTC a $%.2f", quote_amount, quantity, exec_price)
        
        return OrderExecution(
            order_id=str(uuid.uuid4()),
            client_order_id=client_order_id,
            side="BUY",
            symbol=symbol,
            status="FILLED",
            executed_qty=quantity,
            quote_qty=quote_amount,
            avg_price=exec_price,
            fee_qty=fee_paid,
            fee_asset="USDT",
            timestamp=time.time()
        )

    def create_market_sell(self, symbol: str, quantity: float, client_order_id: str = "") -> OrderExecution:
        # We use the freshest price for the execution
        exec_price = self.get_price(symbol)
        
        if quantity > self.balances["BTC"]:
            raise RuntimeError("BTC insuficiente en paper trading")
            
        gross_quote = quantity * exec_price
        fee_paid = gross_quote * Config.BINANCE_FEE_PCT
        net_quote = gross_quote - fee_paid
        
        self.balances["BTC"] -= quantity
        self.balances["USDT"] += net_quote
        logger.info("Paper SELL %.8f BTC -> %.2f USDT a $%.2f", quantity, net_quote, exec_price)
        
        return OrderExecution(
            order_id=str(uuid.uuid4()),
            client_order_id=client_order_id,
            side="SELL",
            symbol=symbol,
            status="FILLED",
            executed_qty=quantity,
            quote_qty=net_quote,
            avg_price=exec_price,
            fee_qty=fee_paid,
            fee_asset="USDT",
            timestamp=time.time()
        )
