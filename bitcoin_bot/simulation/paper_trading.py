from __future__ import annotations
import logging
import time
import uuid
import random
from decimal import Decimal
from bitcoin_bot.config import Config
from bitcoin_bot.core.models import OrderExecution

logger = logging.getLogger(__name__)

class PaperBinanceClient:
    """
    Simulador de Binance que NO requiere API Keys.
    Puede funcionar de forma 100% offline o con un proveedor de datos.
    """
    def __init__(self, initial_btc: str = "0.01", initial_usdt: str = "1000.0"):
        self.balances = {
            "BTC": Decimal(initial_btc),
            "USDT": Decimal(initial_usdt)
        }
        self.current_price = Decimal("65000.0")
        self.symbol_info = {
            "min_qty": Config.MIN_BTC_TO_SELL,
            "step_size": Config.MIN_BTC_TO_SELL,
            "min_notional": Config.MIN_USDT_TO_OPERATE
        }
        # Proveedor de datos opcional (inyectado externamente si se desea Live Paper)
        self.data_provider = None 

    def reconnect(self) -> None:
        pass

    def get_price(self, symbol: str) -> Decimal:
        if self.data_provider:
            self.current_price = self.data_provider.get_price(symbol)
        return self.current_price

    def set_price(self, price: Decimal | float) -> None:
        self.current_price = Decimal(str(price))

    def get_balance(self, asset: str) -> Decimal:
        return self.balances.get(asset, Decimal("0.0"))

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
        return self.symbol_info

    def get_klines(self, symbol: str, interval: str, limit: int = 14) -> list:
        if self.data_provider:
            return self.data_provider.get_klines(symbol, interval, limit)
            
        # Mock klines offline
        klines = []
        now = int(time.time() * 1000)
        base = self.current_price
        for i in range(limit):
            var = Decimal(str(random.uniform(-0.01, 0.01)))
            close_p = base * (Decimal("1") + var)
            klines.append([
                now - (limit - i) * 3600000,
                str(base), str(max(base, close_p) * Decimal("1.001")), 
                str(min(base, close_p) * Decimal("0.999")), str(close_p), "0"
            ])
            base = close_p
        return klines

    def get_order_status(self, symbol: str, client_order_id: str) -> OrderExecution | None:
        return None

    def create_market_buy(self, symbol: str, quote_amount: Decimal | float, client_order_id: str = "") -> OrderExecution:
        quote_amount = Decimal(str(quote_amount))
        if quote_amount > self.balances["USDT"]:
            raise RuntimeError("USDT insuficiente en paper trading")
            
        fee_paid = quote_amount * Config.BINANCE_FEE_PCT
        quantity = (quote_amount - fee_paid) / self.current_price
        
        self.balances["USDT"] -= quote_amount
        self.balances["BTC"] += quantity
        
        logger.info("Paper BUY %.2f USDT -> %.8f BTC a $%.2f", quote_amount, quantity, self.current_price)
        
        return OrderExecution(
            order_id=str(uuid.uuid4()),
            client_order_id=client_order_id,
            side="BUY",
            symbol=symbol,
            status="FILLED",
            executed_qty=quantity,
            quote_qty=quote_amount,
            avg_price=self.current_price,
            fee_qty=fee_paid,
            fee_asset="USDT",
            fee_in_usdt=fee_paid,
            timestamp=time.time()
        )

    def create_market_sell(self, symbol: str, quantity: Decimal | float, client_order_id: str = "") -> OrderExecution:
        quantity = Decimal(str(quantity))
        if quantity > self.balances["BTC"]:
            raise RuntimeError("BTC insuficiente en paper trading")
            
        gross_quote = quantity * self.current_price
        fee_paid = gross_quote * Config.BINANCE_FEE_PCT
        net_quote = gross_quote - fee_paid
        
        self.balances["BTC"] -= quantity
        self.balances["USDT"] += net_quote
        
        logger.info("Paper SELL %.8f BTC -> %.2f USDT a $%.2f", quantity, net_quote, self.current_price)
        
        return OrderExecution(
            order_id=str(uuid.uuid4()),
            client_order_id=client_order_id,
            side="SELL",
            symbol=symbol,
            status="FILLED",
            executed_qty=quantity,
            quote_qty=net_quote,
            avg_price=self.current_price,
            fee_qty=fee_paid,
            fee_asset="USDT",
            fee_in_usdt=fee_paid,
            timestamp=time.time()
        )
