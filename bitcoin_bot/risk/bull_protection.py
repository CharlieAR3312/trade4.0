from __future__ import annotations
from bitcoin_bot.config import Config

class BullProtection:
    def current_buy_threshold(self, state_machine) -> float:
        # Desactivado para Active Scalper. Usaremos RSI.
        return Config.BASE_BUY_LEVEL_1_PCT

    def force_buy_plan(self, state_machine) -> dict | None:
        # Desactivado para evitar compras con FOMO en Active Scalper.
        return None
