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
    total_usdt_invested: float = 0.0
    average_buy_price: float = 0.0
    total_btc_bought: float = 0.0

class StateMachine:
    def __init__(self):
        self.state = BotState.NEUTRO
        self.state_since = time.time()
        self.last_operation_ts = None
        self.buy_level_1_done = False
        self.buy_level_2_done = False
        self.usdt_idle_since = None
        self.total_usdt_invested = 0.0
        self.average_buy_price = 0.0
        self.total_btc_bought = 0.0
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

    def register_sell(self, btc_sold: float = 0.0, full_sell: bool = True) -> None:
        if full_sell or btc_sold >= self.total_btc_bought * 0.99:
            self.buy_level_1_done = False
            self.buy_level_2_done = False
            self.total_usdt_invested = 0.0
            self.average_buy_price = 0.0
            self.total_btc_bought = 0.0
        else:
            self.total_btc_bought -= btc_sold
            self.total_usdt_invested = self.total_btc_bought * self.average_buy_price
            if self.total_usdt_invested <= 0:
                self.buy_level_1_done = False
                self.buy_level_2_done = False
        self.register_operation("VENTA")

    def register_buy(self, level: int, usdt_amount: float = 0.0, btc_amount: float = 0.0, price: float = 0.0) -> None:
        if level == 1:
            self.buy_level_1_done = True
        elif level == 2:
            self.buy_level_2_done = True
        
        if btc_amount > 0 and usdt_amount > 0:
            new_total_btc = self.total_btc_bought + btc_amount
            new_total_cost = self.total_usdt_invested + usdt_amount
            self.average_buy_price = new_total_cost / new_total_btc
            self.total_btc_bought = new_total_btc
            self.total_usdt_invested = new_total_cost
            
        self.register_operation(f"COMPRA_NIVEL_{level}")

    def check_reconciliation(self, real_btc_balance: float) -> None:
        if self.state == BotState.MODO_SEGURO:
            return
        diff = abs(real_btc_balance - self.total_btc_bought)
        # Permite una tolerancia muy pequeña (ej. polvo dejado por comisiones)
        if diff > getattr(Config, "MIN_BTC_TO_SELL", 0.0001):
            logger.critical("Inconsistencia detectada: DB tiene %.8f BTC, Exchange tiene %.8f BTC", self.total_btc_bought, real_btc_balance)
            self.enter_safe_mode("Inconsistencia de balance detectada. Reconciliacion manual requerida.")

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
        payload = asdict(StateSnapshot(
            state=self.state.value, 
            state_since=self.state_since, 
            last_operation_ts=self.last_operation_ts, 
            buy_level_1_done=self.buy_level_1_done, 
            buy_level_2_done=self.buy_level_2_done, 
            usdt_idle_since=self.usdt_idle_since, 
            total_usdt_invested=self.total_usdt_invested,
            average_buy_price=self.average_buy_price,
            total_btc_bought=self.total_btc_bought
        ))
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
        machine.total_usdt_invested = float(payload.get("total_usdt_invested", 0.0))
        machine.average_buy_price = float(payload.get("average_buy_price", 0.0))
        machine.total_btc_bought = float(payload.get("total_btc_bought", 0.0))
        machine.history = list(payload.get("history", []))
        return machine
