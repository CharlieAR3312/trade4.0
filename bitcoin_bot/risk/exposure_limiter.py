from __future__ import annotations
from bitcoin_bot.config import Config

class ExposureLimiter:
    def sell_quantity(self, btc_balance: float) -> float:
        return btc_balance * Config.MAX_SELL_PCT_PER_CYCLE
