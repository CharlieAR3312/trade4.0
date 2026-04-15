from __future__ import annotations
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from bitcoin_bot.config import Config

logger = logging.getLogger(__name__)

class BotState(Enum):
    NEUTRO = "NEUTRO"
    EN_SUBIDA = "EN_SUBIDA"
    EN_BAJADA = "EN_BAJADA"
    ENFRIANDO = "ENFRIANDO"
    MODO_SEGURO = "MODO_SEGURO"

@dataclass
class StateSnapshot:
    state: str = BotState.NEUTRO.value
    state_since: float | None = None
    last_operation_ts: float | None = None
    buy_level_1_done: bool = False
    buy_level_2_done: bool = False
    usdt_idle_since: float | None = None

class StateMachine:
    def __init__(self):
        self.state = BotState.NEUTRO
        self.state_since = time.time()
        self.last_operation_ts = None
        self.buy_level_1_done = False
        self.buy_level_2_done = False
        self.usdt_idle_since = None
        self.history: list[dict] = []

    def transition(self, new_state: BotState, reason: str = "") -> None:
        if self.state == new_state:
            return
        old_state = self.state
        self.state = new_state
        self.state_since = time.time()
        self.history.append({"from": old_state.value, "to": new_state.value, "reason": reason, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        if len(self.history) > 100:
            self.history.pop(0)
        logger.info("Estado %s -> %s | %s", old_state.value, new_state.value, reason)

    def register_operation(self, operation_type: str) -> None:
        self.last_operation_ts = time.time()
        self.transition(BotState.ENFRIANDO, f"Operacion: {operation_type}")

    def register_sell(self) -> None:
        self.buy_level_1_done = False
        self.buy_level_2_done = False
        self.register_operation("VENTA")

    def register_buy(self, level: int) -> None:
        if level == 1:
            self.buy_level_1_done = True
        elif level == 2:
            self.buy_level_2_done = True
        self.register_operation(f"COMPRA_NIVEL_{level}")

    def register_usdt_received(self) -> None:
        self.usdt_idle_since = time.time()

    def register_usdt_spent(self) -> None:
        self.usdt_idle_since = None

    def is_cooling_down(self) -> bool:
        if self.state != BotState.ENFRIANDO or self.last_operation_ts is None:
            return False
        elapsed_minutes = (time.time() - self.last_operation_ts) / 60
        if elapsed_minutes >= Config.COOLDOWN_MINUTES:
            self.transition(BotState.NEUTRO, "Cooldown completado")
            return False
        return True

    def usdt_idle_days(self) -> float:
        if self.usdt_idle_since is None:
            return 0.0
        return (time.time() - self.usdt_idle_since) / 86400

    def is_safe(self) -> bool:
        return self.state != BotState.MODO_SEGURO

    def enter_safe_mode(self, reason: str) -> None:
        self.transition(BotState.MODO_SEGURO, reason)
        logger.critical("Modo seguro: %s", reason)

    def to_dict(self) -> dict:
        payload = asdict(StateSnapshot(state=self.state.value, state_since=self.state_since, last_operation_ts=self.last_operation_ts, buy_level_1_done=self.buy_level_1_done, buy_level_2_done=self.buy_level_2_done, usdt_idle_since=self.usdt_idle_since))
        payload["history"] = self.history
        return payload

    @classmethod
    def from_dict(cls, payload: dict | None) -> "StateMachine":
        machine = cls()
        if not payload:
            return machine
        machine.state = BotState(payload.get("state", BotState.NEUTRO.value))
        machine.state_since = payload.get("state_since") or time.time()
        machine.last_operation_ts = payload.get("last_operation_ts")
        machine.buy_level_1_done = bool(payload.get("buy_level_1_done"))
        machine.buy_level_2_done = bool(payload.get("buy_level_2_done"))
        machine.usdt_idle_since = payload.get("usdt_idle_since")
        machine.history = list(payload.get("history", []))
        return machine
