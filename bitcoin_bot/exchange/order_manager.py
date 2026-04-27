from __future__ import annotations
import logging
import time
import uuid
from bitcoin_bot.config import Config
from bitcoin_bot.core.models import OrderExecution

logger = logging.getLogger(__name__)

class OrderManager:
    def __init__(self, market_client):
        self.market_client = market_client

    def market_buy(self, quote_amount: float) -> OrderExecution | None:
        return self._execute("BUY", quote_amount=quote_amount)

    def market_sell(self, quantity: float) -> OrderExecution | None:
        return self._execute("SELL", quantity=quantity)

    def _execute(self, side: str, quote_amount: float | None = None, quantity: float | None = None) -> OrderExecution | None:
        client_order_id = str(uuid.uuid4())
        
        for attempt in range(1, Config.ORDER_MAX_RETRIES + 1):
            try:
                # Before retrying, check if the order actually went through but we missed the response
                if attempt > 1:
                    existing_order = self.market_client.get_order_status(Config.SYMBOL, client_order_id)
                    if existing_order and existing_order.status in ["FILLED", "PARTIALLY_FILLED"]:
                        logger.info("Orden %s ya habia sido ejecutada silenciosamente en el intento anterior.", side)
                        return existing_order
                
                if side == "BUY":
                    result = self.market_client.create_market_buy(Config.SYMBOL, quote_amount, client_order_id)
                else:
                    result = self.market_client.create_market_sell(Config.SYMBOL, quantity, client_order_id)
                    
                logger.info("Orden %s ejecutada en intento %s", side, attempt)
                return result
                
            except Exception as exc:
                logger.warning("Fallo orden %s intento %s: %s", side, attempt, exc)
                if attempt == Config.ORDER_MAX_RETRIES:
                    break
                time.sleep(Config.ORDER_RETRY_BASE_SECONDS * (2 ** (attempt - 1)))
                
        return None
