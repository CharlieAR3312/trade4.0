from __future__ import annotations
from decimal import Decimal, ROUND_DOWN
from bitcoin_bot.config import Config

class Validator:
    def __init__(self, market_client):
        self.market_client = market_client
        self.symbol_info = self.market_client.get_symbol_info(Config.SYMBOL) or {
            "min_qty": Config.MIN_BTC_TO_SELL,
            "step_size": Config.MIN_BTC_TO_SELL,
            "min_notional": Config.MIN_USDT_TO_OPERATE,
        }

    def validate_buy(self, quote_amount: float) -> dict:
        if quote_amount < Config.MIN_USDT_TO_OPERATE:
            return {"ok": False, "reason": "USDT insuficiente para operar"}
        if quote_amount < self.symbol_info["min_notional"]:
            return {"ok": False, "reason": "No alcanza el notional minimo del par"}
        return {"ok": True, "quote_amount": round(quote_amount, 2)}

    def validate_sell(self, quantity: float, price: float) -> dict:
        normalized = self._round_step(quantity, self.symbol_info["step_size"])
        if normalized < max(Config.MIN_BTC_TO_SELL, self.symbol_info["min_qty"]):
            return {"ok": False, "reason": "Cantidad BTC por debajo del minimo"}
        if normalized * Decimal(str(price)) < Decimal(str(self.symbol_info["min_notional"])):
            return {"ok": False, "reason": "La venta no cumple el notional minimo"}
        return {"ok": True, "quantity": float(normalized)}

    @staticmethod
    def _round_step(quantity: float, step: float) -> Decimal:
        return Decimal(str(quantity)).quantize(Decimal(str(step)), rounding=ROUND_DOWN)
