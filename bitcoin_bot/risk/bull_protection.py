from __future__ import annotations
from bitcoin_bot.config import Config

class BullProtection:
    def current_buy_threshold(self, state_machine) -> float:
        if state_machine.usdt_idle_days() >= Config.BULL_PROTECTION_DAYS:
            return Config.BULL_REDUCED_BUY_PCT
        return Config.BUY_LEVEL_1_PCT

    def force_buy_plan(self, state_machine) -> dict | None:
        idle_days = state_machine.usdt_idle_days()
        if idle_days >= Config.BULL_FORCE_BUY_DAYS:
            return {"fraction": Config.BULL_FORCE_BUY_USDT_PCT, "reason": f"USDT idle por {idle_days:.1f} dias"}
        return None
