from __future__ import annotations
import logging
import time
from bitcoin_bot.config import Config

logger = logging.getLogger(__name__)

class OrderManager:
    def __init__(self, market_client):
        self.market_client = market_client

    def market_buy(self, quote_amount: float) -> dict | None:
        return self._execute("BUY", quote_amount=quote_amount)

    def market_sell(self, quantity: float) -> dict | None:
        return self._execute("SELL", quantity=quantity)

    def _execute(self, side: str, quote_amount: float | None = None, quantity: float | None = None) -> dict | None:
        for attempt in range(1, Config.ORDER_MAX_RETRIES + 1):
            try:
                if side == "BUY":
                    result = self.market_client.create_market_buy(Config.SYMBOL, quote_amount)
                else:
                    result = self.market_client.create_market_sell(Config.SYMBOL, quantity)
                logger.info("Orden %s ejecutada en intento %s", side, attempt)
                return result
            except Exception as exc:
                logger.warning("Fallo orden %s intento %s: %s", side, attempt, exc)
                if attempt == Config.ORDER_MAX_RETRIES:
                    break
                time.sleep(Config.ORDER_RETRY_BASE_SECONDS * (2 ** (attempt - 1)))
        return None
