from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
import time

@dataclass
class OrderExecution:
    order_id: str
    client_order_id: str
    side: str  # BUY / SELL
    symbol: str
    status: str
    executed_qty: Decimal
    quote_qty: Decimal
    avg_price: Decimal
    fee_qty: Decimal
    fee_asset: str
    timestamp: float = field(default_factory=time.time)
    
    # Normalizacion de comisiones
    fee_in_usdt: Decimal = Decimal("0.0")

    def __post_init__(self):
        # Asegurar que todos los campos numericos sean Decimal
        self.executed_qty = Decimal(str(self.executed_qty))
        self.quote_qty = Decimal(str(self.quote_qty))
        self.avg_price = Decimal(str(self.avg_price))
        self.fee_qty = Decimal(str(self.fee_qty))
        if self.fee_in_usdt:
            self.fee_in_usdt = Decimal(str(self.fee_in_usdt))

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "side": self.side,
            "symbol": self.symbol,
            "status": self.status,
            "executed_qty": str(self.executed_qty),
            "quote_qty": str(self.quote_qty),
            "avg_price": str(self.avg_price),
            "fee_qty": str(self.fee_qty),
            "fee_asset": self.fee_asset,
            "fee_in_usdt": str(self.fee_in_usdt),
            "timestamp": self.timestamp
        }
