from __future__ import annotations
from decimal import Decimal
from bitcoin_bot.config import Config

class FeeCalculator:
    def round_trip_fee_pct(self) -> Decimal:
        return Config.BINANCE_FEE_PCT * Decimal("2")

    def estimated_net_move(self, gross_move_pct: Decimal) -> Decimal:
        return gross_move_pct - self.round_trip_fee_pct()

    def is_profitable(self, gross_move_pct: Decimal) -> bool:
        if gross_move_pct <= 0:
            return False
        net_move = self.estimated_net_move(gross_move_pct)
        if net_move <= 0:
            return False
        return (net_move / gross_move_pct) >= Config.MIN_NET_GAIN_RATIO
