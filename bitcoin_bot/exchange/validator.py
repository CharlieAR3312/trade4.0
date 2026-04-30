from __future__ import annotations
from decimal import Decimal, ROUND_DOWN
from bitcoin_bot.config import Config

class Validator:
    def __init__(self, market_client):
        self.market_client = market_client
        info = self.market_client.get_symbol_info(Config.SYMBOL)
        self.symbol_info = info if info else {
            "min_qty": Config.MIN_BTC_TO_SELL,
            "step_size": Config.MIN_BTC_TO_SELL,
            "min_notional": Config.MIN_USDT_TO_OPERATE,
        }

    def validate_buy(self, quote_amount: Decimal | float) -> dict:
        quote_amount = Decimal(str(quote_amount))
        if quote_amount < Config.MIN_USDT_TO_OPERATE:
            return {"ok": False, "reason": f"USDT {quote_amount} insuficiente"}
            
        min_notional = Decimal(str(self.symbol_info["min_notional"]))
        if quote_amount < min_notional:
            return {"ok": False, "reason": f"Notional minimo {min_notional} no alcanzado"}
            
        return {"ok": True, "quote_amount": quote_amount.quantize(Decimal("0.01"), rounding=ROUND_DOWN)}

    def validate_sell(self, quantity: Decimal | float, price: Decimal | float) -> dict:
        quantity = Decimal(str(quantity))
        price = Decimal(str(price))
        
        step_size = Decimal(str(self.symbol_info["step_size"]))
        normalized = self._round_step(quantity, step_size)
        
        min_qty = Decimal(str(self.symbol_info["min_qty"]))
        if normalized < max(Config.MIN_BTC_TO_SELL, min_qty):
            return {"ok": False, "reason": f"Cantidad {normalized} BTC por debajo del minimo"}
            
        min_notional = Decimal(str(self.symbol_info["min_notional"]))
        if normalized * price < min_notional:
            return {"ok": False, "reason": f"Venta {normalized*price} USDT no cumple notional minimo {min_notional}"}
            
        return {"ok": True, "quantity": normalized}

    @staticmethod
    def _round_step(quantity: Decimal, step: Decimal) -> Decimal:
        return quantity.quantize(step, rounding=ROUND_DOWN)
