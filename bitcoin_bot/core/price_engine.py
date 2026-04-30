from __future__ import annotations
import logging
import time
from datetime import datetime
from decimal import Decimal
from bitcoin_bot.config import Config

logger = logging.getLogger(__name__)

class PriceEngine:
    def __init__(self, market_client, engine_state=None):
        self.client = market_client
        self.engine_state = engine_state
        self.current_price: Decimal | None = None
        self.peak_price: Decimal | None = None
        self.last_updated: float | None = None
        self.price_history: list[dict] = []
        self.error_count = 0
        self.max_errors = 5

    def fetch_price(self) -> Decimal | None:
        try:
            price = self.client.get_price(Config.SYMBOL)
            if price is None or price <= 0:
                raise ValueError(f"Precio invalido: {price}")
            
            price = Decimal(str(price))
            self.error_count = 0
            self.current_price = price
            self.last_updated = time.time()
            
            if self.peak_price is None or price > self.peak_price:
                self.peak_price = price
            
            self.price_history.append({
                "price": str(price), 
                "timestamp": self.last_updated, 
                "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            if len(self.price_history) > 200:
                self.price_history.pop(0)
            
            logger.info("BTC/USDT %.2f | Pico %.2f", float(price), float(self.peak_price))
            return price
        except Exception as exc:
            self.error_count += 1
            logger.warning("Fallo consultando precio (%s/%s): %s", self.error_count, self.max_errors, exc)
            if self.error_count >= self.max_errors:
                self._handle_connection_loss()
            return None

    def reset_peak(self, new_peak: Decimal | float | None = None) -> None:
        if new_peak is not None:
            self.peak_price = Decimal(str(new_peak))
        else:
            self.peak_price = self.current_price
            
        if self.peak_price is not None:
            logger.info("Pico reseteado a %.2f", float(self.peak_price))

    def is_fresh(self) -> bool:
        return self.last_updated is not None and (time.time() - self.last_updated) < (Config.PRICE_INTERVAL_SECONDS + 5)

    def get_change_from_base(self, base_price: Decimal | float | None) -> Decimal:
        if self.current_price is None or base_price in (None, 0):
            return Decimal("0.0")
        base_price = Decimal(str(base_price))
        return (self.current_price - base_price) / base_price

    def get_drop_from_peak(self) -> Decimal:
        if self.current_price is None or self.peak_price in (None, 0):
            return Decimal("0.0")
        return (self.current_price - self.peak_price) / self.peak_price

    def run_loop(self, callback) -> None:
        logger.info("Motor de precios iniciado con intervalo de %ss", Config.PRICE_INTERVAL_SECONDS)
        while True:
            if self.engine_state:
                if self.engine_state.is_stopped():
                    logger.info("Motor global detenido. Saliendo del loop...")
                    break
                if self.engine_state.is_paused():
                    time.sleep(2)
                    continue

            try:
                self.fetch_price()
                if self.current_price is not None:
                    callback(self)
                time.sleep(Config.PRICE_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                logger.info("Bot detenido manualmente")
                break
            except Exception as exc:
                logger.exception("Error en loop principal: %s", exc)
                time.sleep(Config.PRICE_INTERVAL_SECONDS)

    def _handle_connection_loss(self) -> None:
        for wait_seconds in (10, 30, 60, 120):
            logger.warning("Intentando reconectar en %ss", wait_seconds)
            time.sleep(wait_seconds)
            try:
                self.client.reconnect()
                self.error_count = 0
                logger.info("Reconectado a Binance")
                return
            except Exception:
                continue
        raise ConnectionError("No fue posible restablecer la conexion con Binance")
