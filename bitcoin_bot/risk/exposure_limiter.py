from __future__ import annotations
from decimal import Decimal
from bitcoin_bot.config import Config

class ExposureLimiter:
    def sell_quantity(self, btc_balance: Decimal, current_price: Decimal, usdt_to_recover: Decimal) -> Decimal:
        """
        Calcula la cantidad de BTC a vender para recuperar exactamente el USDT invertido.
        El excedente (profit) se queda en BTC.
        """
        if usdt_to_recover <= 0 or current_price <= 0:
            return Decimal("0.0")
            
        # gross_usdt = net_usdt / (1 - fee)
        required_gross_usdt = usdt_to_recover / (Decimal("1") - Config.BINANCE_FEE_PCT)
        
        required_btc = required_gross_usdt / current_price
        
        if required_btc > btc_balance:
            return btc_balance
            
        return required_btc
