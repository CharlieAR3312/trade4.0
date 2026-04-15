from __future__ import annotations
import csv
from pathlib import Path

class TradeLog:
    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.fieldnames = ["timestamp", "mode", "side", "symbol", "price", "quantity", "quote_amount", "fee_paid", "reason"]
        if not self.filepath.exists():
            with self.filepath.open("w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=self.fieldnames).writeheader()

    def append(self, trade: dict) -> None:
        row = {key: trade.get(key, "") for key in self.fieldnames}
        with self.filepath.open("a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=self.fieldnames).writerow(row)
