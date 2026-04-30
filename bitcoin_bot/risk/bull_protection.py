from __future__ import annotations
from decimal import Decimal
from bitcoin_bot.config import Config

class BullProtection:
    def current_buy_threshold(self, state_machine) -> Decimal:
        return Config.BASE_BUY_LEVEL_1_PCT

    def force_buy_plan(self, state_machine) -> dict | None:
        return None
