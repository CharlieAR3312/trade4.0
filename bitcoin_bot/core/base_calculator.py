from __future__ import annotations
import logging
import time
from dataclasses import asdict, dataclass

logger = logging.getLogger(__name__)

@dataclass
class BaseSnapshot:
    price: float | None = None
    updated_at: float | None = None
    source: str = "startup"

class BaseCalculator:
    def __init__(self, initial_price: float | None = None):
        self.snapshot = BaseSnapshot(price=initial_price, updated_at=time.time() if initial_price else None)

    @property
    def base_price(self) -> float | None:
        return self.snapshot.price

    def initialize(self, price: float) -> None:
        if self.snapshot.price is None:
            self.update(price, "initial_price")

    def update(self, price: float, source: str) -> None:
        self.snapshot = BaseSnapshot(price=price, updated_at=time.time(), source=source)
        logger.info("Base flotante actualizada a %.2f (%s)", price, source)

    def to_dict(self) -> dict:
        return asdict(self.snapshot)

    @classmethod
    def from_dict(cls, payload: dict | None) -> "BaseCalculator":
        calc = cls()
        if payload:
            calc.snapshot = BaseSnapshot(price=payload.get("price"), updated_at=payload.get("updated_at"), source=payload.get("source", "restored"))
        return calc
