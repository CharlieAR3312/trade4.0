from __future__ import annotations
import logging
import os
import time
from dotenv import load_dotenv

try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
except ImportError:
    Client = None
    BinanceAPIException = Exception

logger = logging.getLogger(__name__)
from pathlib import Path as _Path; load_dotenv(_Path(__file__).resolve().parent.parent / ".env")

class BinanceClient:
    def __init__(self):
        self.api_key = os.getenv("BINANCE_API_KEY")
        self.secret_key = os.getenv("BINANCE_SECRET_KEY")
        self.client = None
        self._connect()

    def _connect(self) -> None:
        if Client is None:
            raise RuntimeError("python-binance no esta instalado")
        if not self.api_key or not self.secret_key:
            raise RuntimeError("Faltan BINANCE_API_KEY y BINANCE_SECRET_KEY")
        self.client = Client(self.api_key, self.secret_key)
        self.client.ping()
        logger.info("Conectado a Binance")

    def reconnect(self) -> None:
        time.sleep(5)
        self._connect()

    def get_price(self, symbol: str) -> float | None:
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return float(ticker["price"])
        except BinanceAPIException as exc:
            logger.error("Error obteniendo precio: %s", exc)
            return None

    def get_balance(self, asset: str) -> float:
        try:
            balance = self.client.get_asset_balance(asset=asset)
            return float(balance["free"])
        except BinanceAPIException as exc:
            logger.error("Error obteniendo saldo %s: %s", asset, exc)
            return 0.0

    def get_portfolio_snapshot(self, symbol: str) -> dict | None:
        btc_balance = self.get_balance("BTC")
        usdt_balance = self.get_balance("USDT")
        btc_price = self.get_price(symbol)
        if btc_price is None:
            return None
        btc_value_usdt = btc_balance * btc_price
        return {"btc_balance": btc_balance, "usdt_balance": usdt_balance, "btc_price": btc_price, "btc_value_usdt": btc_value_usdt, "total_usdt": btc_value_usdt + usdt_balance, "timestamp": time.time()}

    def get_symbol_info(self, symbol: str) -> dict | None:
        try:
            info = self.client.get_symbol_info(symbol)
            filters = {item["filterType"]: item for item in info["filters"]}
            return {"min_qty": float(filters["LOT_SIZE"]["minQty"]), "step_size": float(filters["LOT_SIZE"]["stepSize"]), "min_notional": float(filters["MIN_NOTIONAL"]["minNotional"])}
        except Exception as exc:
            logger.error("Error obteniendo metadatos del simbolo: %s", exc)
            return None

    def create_market_buy(self, symbol: str, quote_amount: float) -> dict:
        return self.client.order_market_buy(symbol=symbol, quoteOrderQty=quote_amount)

    def create_market_sell(self, symbol: str, quantity: float) -> dict:
        return self.client.order_market_sell(symbol=symbol, quantity=quantity)
