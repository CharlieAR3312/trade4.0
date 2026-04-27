from __future__ import annotations
import csv
from pathlib import Path

class TradeLog:
    def __init__(self, db_manager):
        self.db_manager = db_manager

    def append(self, trade: dict) -> None:
        self.db_manager.insert_trade(trade)
