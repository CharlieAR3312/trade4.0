from __future__ import annotations
import logging
import time
from dataclasses import asdict, dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)

@dataclass
class BaseSnapshot:
    price: str | None = None
    updated_at: float | None = None
    source: str = "startup"

class BaseCalculator:
    def __init__(self, initial_price: Decimal | None = None):
        self.snapshot = BaseSnapshot(
            price=str(initial_price) if initial_price else None, 
            updated_at=time.time() if initial_price else None
        )

    @property
    def base_price(self) -> Decimal | None:
        if self.snapshot.price is None: return None
        return Decimal(self.snapshot.price)

    def initialize(self, price: Decimal) -> None:
        if self.snapshot.price is None:
            self.update(price, "initial_price")

    def update(self, price: Decimal, source: str) -> None:
        self.snapshot = BaseSnapshot(price=str(price), updated_at=time.time(), source=source)
        logger.info("Base flotante actualizada a %.2f (%s)", float(price), source)

    def to_dict(self) -> dict:
        return asdict(self.snapshot)

    @classmethod
    def from_dict(cls, payload: dict | None) -> "BaseCalculator":
        calc = cls()
        if payload:
            calc.snapshot = BaseSnapshot(
                price=payload.get("price"), 
                updated_at=payload.get("updated_at"), 
                source=payload.get("source", "restored")
            )
        return calc
