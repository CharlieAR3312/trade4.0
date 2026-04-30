from __future__ import annotations
import logging
import time
from decimal import Decimal
from bitcoin_bot.config import Config

logger = logging.getLogger(__name__)

class VolatilityEngine:
    """
    Calcula el Average True Range (ATR) y el RSI utilizando Klines de Binance 
    para adaptar los umbrales de compra y venta según la volatilidad y el momentum.
    """
    def __init__(self, market_client, period=14):
        self.market_client = market_client
        self.interval = getattr(Config, "KLINES_INTERVAL", "15m")
        self.period = period
        self.rsi_period = getattr(Config, "RSI_PERIOD", 14)
        
        self.current_atr = Decimal("0.0")
        self.current_atr_pct = Decimal("0.0")
        self.current_rsi = Decimal("50.0")
        self.last_update = 0.0
        
        # Umbrales base
        self.buy_threshold_1 = Config.BASE_BUY_LEVEL_1_PCT
        self.buy_threshold_2 = Config.BASE_BUY_LEVEL_2_PCT
        self.sell_threshold = Config.BASE_SELL_THRESHOLD_PCT

    def _calculate_rsi(self, prices: list[Decimal], period: int) -> Decimal:
        if len(prices) < period + 1:
            return Decimal("50.0")
            
        gains = []
        losses = []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(Decimal("0.0"))
            else:
                gains.append(Decimal("0.0"))
                losses.append(abs(change))
        
        avg_gain = sum(gains[:period]) / Decimal(str(period))
        avg_loss = sum(losses[:period]) / Decimal(str(period))
        
        for i in range(period, len(prices) - 1):
            avg_gain = (avg_gain * Decimal(str(period - 1)) + gains[i]) / Decimal(str(period))
            avg_loss = (avg_loss * Decimal(str(period - 1)) + losses[i]) / Decimal(str(period))
            
        if avg_loss == 0:
            return Decimal("100.0")
            
        rs = avg_gain / avg_loss
        return Decimal("100.0") - (Decimal("100.0") / (Decimal("1.0") + rs))

    def update(self) -> None:
        """Actualiza el ATR, RSI y los umbrales dinámicos"""
        if time.time() - self.last_update < 60 and self.current_atr > 0:
            return

        limit = max(100, self.period * 2)
        klines = self.market_client.get_klines(Config.SYMBOL, self.interval, limit)
        if not klines or len(klines) < self.period + 1:
            logger.warning("No hay suficientes Klines para calcular volatilidad y RSI")
            return

        # Closes a Decimal
        closes = [Decimal(str(k[4])) for k in klines]
        self.current_rsi = self._calculate_rsi(closes, self.rsi_period)

        # Calcular ATR
        tr_list = []
        recent_klines = klines[-(self.period + 1):]
        for i in range(1, len(recent_klines)):
            high = Decimal(str(recent_klines[i][2]))
            low = Decimal(str(recent_klines[i][3]))
            prev_close = Decimal(str(recent_klines[i-1][4]))
            
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)

        if not tr_list:
            return

        self.current_atr = sum(tr_list) / Decimal(str(len(tr_list)))
        current_price = closes[-1]
        self.current_atr_pct = self.current_atr / current_price if current_price > 0 else Decimal("0.0")

        self.buy_threshold_1 = max(Config.BASE_BUY_LEVEL_1_PCT, self.current_atr_pct * Config.ATR_MULTIPLIER_BUY_1)
        self.buy_threshold_2 = max(Config.BASE_BUY_LEVEL_2_PCT, self.current_atr_pct * Config.ATR_MULTIPLIER_BUY_2)
        self.sell_threshold = max(Config.BASE_SELL_THRESHOLD_PCT, self.current_atr_pct * Config.ATR_MULTIPLIER_SELL)
        
        self.last_update = time.time()
        logger.info(f"ATR: {self.current_atr_pct*100:.2f}% | RSI: {self.current_rsi:.1f}")
