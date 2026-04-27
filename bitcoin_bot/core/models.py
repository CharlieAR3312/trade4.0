from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class OrderExecution:
    order_id: str
    client_order_id: str
    side: str
    symbol: str
    status: str
    executed_qty: float
    quote_qty: float
    avg_price: float
    fee_qty: float
    fee_asset: str
    timestamp: float
