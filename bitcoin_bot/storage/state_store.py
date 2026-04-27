from __future__ import annotations
import json
from pathlib import Path

class StateStore:
    def __init__(self, db_manager):
        self.db_manager = db_manager

    def load(self) -> dict:
        state = self.db_manager.get_state("main_bot_state")
        return state if state else {}

    def save(self, payload: dict) -> None:
        self.db_manager.set_state("main_bot_state", payload)
