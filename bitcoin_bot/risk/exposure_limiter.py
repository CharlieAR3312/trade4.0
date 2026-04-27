from __future__ import annotations
from bitcoin_bot.config import Config

class ExposureLimiter:
    def sell_quantity(self, btc_balance: float, current_price: float, usdt_to_recover: float) -> float:
        """
        Calcula la cantidad de BTC a vender para recuperar exactamente el USDT invertido.
        El excedente (profit) se queda en BTC.
        """
        if usdt_to_recover <= 0 or current_price <= 0:
            return 0.0
            
        # Añadimos la comisión al cálculo para asegurar que nos llegue el USDT completo
        # net_usdt = gross_usdt - (gross_usdt * fee) -> gross_usdt = net_usdt / (1 - fee)
        required_gross_usdt = usdt_to_recover / (1 - Config.BINANCE_FEE_PCT)
        
        required_btc = required_gross_usdt / current_price
        
        # Nunca vender más de lo que tenemos
        if required_btc > btc_balance:
            return btc_balance
            
        return required_btc
