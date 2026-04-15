from __future__ import annotations
import json
from pathlib import Path

class StateStore:
    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict:
        if not self.filepath.exists():
            return {}
        return json.loads(self.filepath.read_text(encoding="utf-8"))

    def save(self, payload: dict) -> None:
        self.filepath.write_text(json.dumps(payload, indent=2), encoding="utf-8")
