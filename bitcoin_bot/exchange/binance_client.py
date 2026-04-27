from __future__ import annotations
import logging
import os
import time
from dotenv import load_dotenv
from bitcoin_bot.core.models import OrderExecution

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



    def _parse_order_response(self, response: dict) -> OrderExecution:
        total_fee = 0.0
        fee_asset = ""
        avg_price = 0.0
        executed_qty = float(response.get("executedQty", 0.0))
        quote_qty = float(response.get("cummulativeQuoteQty", 0.0))
        
        if executed_qty > 0 and quote_qty > 0:
            avg_price = quote_qty / executed_qty
            
        fills = response.get("fills", [])
        for fill in fills:
            total_fee += float(fill.get("commission", 0.0))
            if not fee_asset:
                fee_asset = fill.get("commissionAsset", "")
                
        # Fallback to general price if fills empty but price exists
        if avg_price == 0.0 and float(response.get("price", 0.0)) > 0:
            avg_price = float(response.get("price", 0.0))
            
        return OrderExecution(
            order_id=str(response.get("orderId", "")),
            client_order_id=response.get("clientOrderId", ""),
            side=response.get("side", ""),
            symbol=response.get("symbol", ""),
            status=response.get("status", "UNKNOWN"),
            executed_qty=executed_qty,
            quote_qty=quote_qty,
            avg_price=avg_price,
            fee_qty=total_fee,
            fee_asset=fee_asset,
            timestamp=float(response.get("transactTime", response.get("time", time.time() * 1000))) / 1000.0
        )

    def get_order_status(self, symbol: str, client_order_id: str) -> OrderExecution | None:
        try:
            order = self.client.get_order(symbol=symbol, origClientOrderId=client_order_id)
            return self._parse_order_response(order)
        except BinanceAPIException as exc:
            logger.error("Error obteniendo status de orden %s: %s", client_order_id, exc)
            return None

    def create_market_buy(self, symbol: str, quote_amount: float, client_order_id: str = "") -> OrderExecution:
        kwargs = {"symbol": symbol, "quoteOrderQty": quote_amount}
        if client_order_id:
            kwargs["newClientOrderId"] = client_order_id
        response = self.client.order_market_buy(**kwargs)
        return self._parse_order_response(response)

    def create_market_sell(self, symbol: str, quantity: float, client_order_id: str = "") -> OrderExecution:
        kwargs = {"symbol": symbol, "quantity": quantity}
        if client_order_id:
            kwargs["newClientOrderId"] = client_order_id
        response = self.client.order_market_sell(**kwargs)
        return self._parse_order_response(response)

    def get_klines(self, symbol: str, interval: str, limit: int = 14) -> list:
        try:
            # klines are returned as list of lists:
            # [ [Open time, Open, High, Low, Close, Volume, Close time, Quote asset volume, Number of trades, Taker buy base asset volume, Taker buy quote asset volume, Ignore] ]
            klines = self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
            return klines
        except Exception as exc:
            logger.error("Error obteniendo klines: %s", exc)
            return []
