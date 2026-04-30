from __future__ import annotations
import logging
import os
import time
from decimal import Decimal
from bitcoin_bot.config import Config
from bitcoin_bot.core.models import OrderExecution

try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
except ImportError:
    Client = None
    BinanceAPIException = Exception

logger = logging.getLogger(__name__)

class BinanceClient:
    def __init__(self):
        self.api_key = Config.BINANCE_API_KEY
        self.secret_key = Config.BINANCE_SECRET_KEY
        self.client = None
        self._connect()

    def _connect(self) -> None:
        if Client is None:
            raise RuntimeError("python-binance no esta instalado")
        if not self.api_key or not self.secret_key:
            raise RuntimeError("BINANCE_API_KEY o SECRET_KEY no configurados (Requeridos para modo Live)")
        
        try:
            self.client = Client(self.api_key, self.secret_key)
            self.client.ping()
            logger.info("Conectado exitosamente a Binance API")
        except Exception as exc:
            logger.error("Fallo conexion inicial a Binance: %s", exc)
            raise

    def reconnect(self) -> None:
        time.sleep(5)
        self._connect()

    def get_price(self, symbol: str) -> Decimal | None:
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return Decimal(ticker["price"])
        except Exception as exc:
            logger.error("Error obteniendo precio: %s", exc)
            return None

    def get_balance(self, asset: str) -> Decimal:
        try:
            balance = self.client.get_asset_balance(asset=asset)
            return Decimal(balance["free"]) if balance else Decimal("0.0")
        except Exception as exc:
            logger.error("Error obteniendo saldo %s: %s", asset, exc)
            return Decimal("0.0")

    def get_portfolio_snapshot(self, symbol: str) -> dict | None:
        btc_balance = self.get_balance("BTC")
        usdt_balance = self.get_balance("USDT")
        btc_price = self.get_price(symbol)
        if btc_price is None:
            return None
        btc_value_usdt = btc_balance * btc_price
        return {
            "btc_balance": btc_balance,
            "usdt_balance": usdt_balance,
            "btc_price": btc_price,
            "btc_value_usdt": btc_value_usdt,
            "total_usdt": btc_value_usdt + usdt_balance,
            "timestamp": time.time()
        }

    def get_symbol_info(self, symbol: str) -> dict | None:
        try:
            info = self.client.get_symbol_info(symbol)
            filters = {item["filterType"]: item for item in info["filters"]}
            return {
                "min_qty": Decimal(filters["LOT_SIZE"]["minQty"]),
                "step_size": Decimal(filters["LOT_SIZE"]["stepSize"]),
                "min_notional": Decimal(filters["MIN_NOTIONAL"]["minNotional"])
            }
        except Exception as exc:
            logger.error("Error obteniendo metadatos del simbolo: %s", exc)
            return None

    def _asset_usdt_price(self, asset: str, fallback_fill_price: Decimal | None = None) -> Decimal | None:
        if asset == "USDT":
            return Decimal("1")
        if asset == "BTC" and fallback_fill_price is not None:
            return Decimal(str(fallback_fill_price))
        try:
            ticker = self.client.get_symbol_ticker(symbol=f"{asset}USDT")
            return Decimal(ticker["price"])
        except Exception as exc:
            logger.error("No fue posible valorar fee en %s contra USDT: %s", asset, exc)
            return None

    def _parse_order_response(self, response: dict) -> OrderExecution:
        # Reconstruccion profunda de Fills para precision contable
        order_id = str(response.get("orderId", ""))
        symbol = response.get("symbol", "")
        side = response.get("side", "")
        
        # Si la respuesta no tiene fills, intentamos recuperarlos de my_trades
        fills = response.get("fills")
        if not fills and response.get("status") == "FILLED":
            try:
                fills = self.client.get_my_trades(symbol=symbol, orderId=order_id)
            except Exception as exc:
                logger.warning("No se pudieron recuperar fills para la orden %s: %s", order_id, exc)

        raw_executed_qty = Decimal(response.get("executedQty", "0.0"))
        raw_quote_qty = Decimal(response.get("cummulativeQuoteQty", "0.0"))
        
        total_fee_qty = Decimal("0.0")
        fee_asset = ""
        fee_in_usdt = Decimal("0.0")
        
        # Procesamiento de Fills y Normalizacion de Comisiones
        if fills:
            for fill in fills:
                f_qty = Decimal(fill.get("commission", "0.0"))
                f_asset = fill.get("commissionAsset", "")
                fill_price = Decimal(fill.get("price", "0.0"))
                total_fee_qty += f_qty
                if not fee_asset: fee_asset = f_asset
                
                fee_price = self._asset_usdt_price(f_asset, fill_price)
                if fee_price is not None:
                    fee_in_usdt += f_qty * fee_price
                else:
                    logger.critical("Fee sin valoracion fiable: %s %s en orden %s", f_qty, f_asset, order_id)

        executed_qty = raw_executed_qty
        quote_qty = raw_quote_qty
        if fee_asset:
            if side == "BUY":
                if fee_asset == "BTC":
                    executed_qty = max(Decimal("0.0"), raw_executed_qty - total_fee_qty)
                elif fee_asset in ("USDT", "BNB"):
                    quote_qty = raw_quote_qty + fee_in_usdt
            elif side == "SELL":
                if fee_asset == "BTC":
                    executed_qty = raw_executed_qty + total_fee_qty
                elif fee_asset == "USDT":
                    quote_qty = max(Decimal("0.0"), raw_quote_qty - total_fee_qty)

        avg_price = Decimal("0.0")
        if raw_executed_qty > 0:
            avg_price = raw_quote_qty / raw_executed_qty

        return OrderExecution(
            order_id=order_id,
            client_order_id=response.get("clientOrderId", ""),
            side=side,
            symbol=symbol,
            status=response.get("status", "UNKNOWN"),
            executed_qty=executed_qty,
            quote_qty=quote_qty,
            avg_price=avg_price,
            fee_qty=total_fee_qty,
            fee_asset=fee_asset,
            fee_in_usdt=fee_in_usdt,
            timestamp=float(response.get("transactTime", response.get("time", time.time() * 1000))) / 1000.0
        )

    def get_order_status(self, symbol: str, client_order_id: str) -> OrderExecution | None:
        try:
            order = self.client.get_order(symbol=symbol, origClientOrderId=client_order_id)
            return self._parse_order_response(order)
        except Exception as exc:
            logger.error("Error obteniendo status de orden %s: %s", client_order_id, exc)
            return None

    def create_market_buy(self, symbol: str, quote_amount: Decimal, client_order_id: str = "") -> OrderExecution:
        kwargs = {"symbol": symbol, "quoteOrderQty": str(quote_amount)}
        if client_order_id:
            kwargs["newClientOrderId"] = client_order_id
        response = self.client.order_market_buy(**kwargs)
        return self._parse_order_response(response)

    def create_market_sell(self, symbol: str, quantity: Decimal, client_order_id: str = "") -> OrderExecution:
        kwargs = {"symbol": symbol, "quantity": str(quantity)}
        if client_order_id:
            kwargs["newClientOrderId"] = client_order_id
        response = self.client.order_market_sell(**kwargs)
        return self._parse_order_response(response)

    def get_klines(self, symbol: str, interval: str, limit: int = 14) -> list:
        try:
            return self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
        except Exception as exc:
            logger.error("Error obteniendo klines: %s", exc)
            return []
