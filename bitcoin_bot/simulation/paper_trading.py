from __future__ import annotations
import logging
import time
from bitcoin_bot.config import Config

logger = logging.getLogger(__name__)

class PaperBinanceClient:
    def __init__(self, initial_btc: float = 0.01, initial_usdt: float = 1000.0, starting_price: float = 65000.0):
        self.balances = {"BTC": initial_btc, "USDT": initial_usdt}
        self.current_price = starting_price
        self.symbol_info = {"min_qty": Config.MIN_BTC_TO_SELL, "step_size": Config.MIN_BTC_TO_SELL, "min_notional": Config.MIN_USDT_TO_OPERATE}

    def reconnect(self) -> None:
        return None

    def get_price(self, symbol: str) -> float:
        return self.current_price

    def set_price(self, price: float) -> None:
        self.current_price = price

    def get_balance(self, asset: str) -> float:
        return self.balances.get(asset, 0.0)

    def get_portfolio_snapshot(self, symbol: str) -> dict:
        btc_value_usdt = self.balances["BTC"] * self.current_price
        return {"btc_balance": self.balances["BTC"], "usdt_balance": self.balances["USDT"], "btc_price": self.current_price, "btc_value_usdt": btc_value_usdt, "total_usdt": btc_value_usdt + self.balances["USDT"], "timestamp": time.time()}

    def get_symbol_info(self, symbol: str) -> dict:
        return self.symbol_info

    def create_market_buy(self, symbol: str, quote_amount: float) -> dict:
        if quote_amount > self.balances["USDT"]:
            raise RuntimeError("USDT insuficiente en paper trading")
        fee_paid = quote_amount * Config.BINANCE_FEE_PCT
        quantity = (quote_amount - fee_paid) / self.current_price
        self.balances["USDT"] -= quote_amount
        self.balances["BTC"] += quantity
        logger.info("Paper BUY %.2f USDT -> %.8f BTC", quote_amount, quantity)
        return {"side": "BUY", "symbol": symbol, "price": self.current_price, "quantity": quantity, "quote_amount": quote_amount, "fee_paid": fee_paid, "mode": "paper", "timestamp": time.time()}

    def create_market_sell(self, symbol: str, quantity: float) -> dict:
        if quantity > self.balances["BTC"]:
            raise RuntimeError("BTC insuficiente en paper trading")
        gross_quote = quantity * self.current_price
        fee_paid = gross_quote * Config.BINANCE_FEE_PCT
        net_quote = gross_quote - fee_paid
        self.balances["BTC"] -= quantity
        self.balances["USDT"] += net_quote
        logger.info("Paper SELL %.8f BTC -> %.2f USDT", quantity, net_quote)
        return {"side": "SELL", "symbol": symbol, "price": self.current_price, "quantity": quantity, "quote_amount": net_quote, "fee_paid": fee_paid, "mode": "paper", "timestamp": time.time()}
