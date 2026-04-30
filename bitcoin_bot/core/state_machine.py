from __future__ import annotations
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from decimal import Decimal
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
    
    # Contabilidad Segura (Decimal como String para JSON)
    active_cost_usdt: str = "0.0"
    active_btc: str = "0.0"
    accumulated_btc: str = "0.0"
    baseline_btc: str | None = None  # Balance inicial de la cuenta para reconciliacion relativa

class StateMachine:
    def __init__(self):
        self.state = BotState.NEUTRO
        self.state_since = time.time()
        self.last_operation_ts = None
        self.buy_level_1_done = False
        self.buy_level_2_done = False
        self.usdt_idle_since = None
        
        # Ledger Interno (Decimal)
        self.active_cost_usdt = Decimal("0.0")
        self.active_btc = Decimal("0.0")
        self.accumulated_btc = Decimal("0.0")
        self.baseline_btc: Decimal | None = None
        
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

    def register_sell(self, btc_sold: Decimal, quote_received: Decimal, full_sell: bool = True) -> None:
        btc_sold = Decimal(str(btc_sold))
        quote_received = Decimal(str(quote_received))
        
        if full_sell or btc_sold >= self.active_btc * Decimal("0.99"):
            # Venta de salida o Stop Loss
            self.buy_level_1_done = False
            self.buy_level_2_done = False
            self.active_cost_usdt = Decimal("0.0")
            self.active_btc = Decimal("0.0")
            logger.info("Posicion activa CERRADA.")
        else:
            # Venta parcial (Profit Split)
            # Primero recuperamos capital
            recovered = min(self.active_cost_usdt, quote_received)
            self.active_cost_usdt -= recovered
            
            # El BTC vendido sale de la posicion activa
            self.active_btc -= btc_sold
            
            # Si recuperamos todo el capital, lo que quede en active_btc pasa a ser ganancia acumulada
            if self.active_cost_usdt <= 0:
                logger.info("Capital recuperado. Transfiriendo %.8f BTC a beneficios acumulados.", self.active_btc)
                self.accumulated_btc += self.active_btc
                self.active_btc = Decimal("0.0")
                self.active_cost_usdt = Decimal("0.0")
                self.buy_level_1_done = False
                self.buy_level_2_done = False

        self.register_operation("VENTA")

    def register_buy(self, level: int, usdt_spent: Decimal, btc_received: Decimal) -> None:
        usdt_spent = Decimal(str(usdt_spent))
        btc_received = Decimal(str(btc_received))
        
        if level == 1:
            self.buy_level_1_done = True
        elif level == 2:
            self.buy_level_2_done = True
        
        self.active_btc += btc_received
        self.active_cost_usdt += usdt_spent
        
        avg = self.active_cost_usdt / self.active_btc if self.active_btc > 0 else 0
        logger.info("Compra Nivel %d: +%.8f BTC | Costo Activo: %.2f USDT | Avg: %.2f", level, btc_received, self.active_cost_usdt, avg)
            
        self.register_operation(f"COMPRA_NIVEL_{level}")

    def check_reconciliation(self, real_btc_balance: Decimal) -> None:
        real_btc_balance = Decimal(str(real_btc_balance))
        
        if self.baseline_btc is None:
            self.baseline_btc = real_btc_balance
            logger.info("Baseline BTC establecido en %.8f (Balance inicial de cuenta)", self.baseline_btc)
            return

        if self.state == BotState.MODO_SEGURO:
            return

        # Delta esperado segun el bot = (BTC actual en estrategia + Ganancia acumulada)
        expected_delta = self.active_btc + self.accumulated_btc
        # Delta real en el exchange respecto al inicio
        actual_delta = real_btc_balance - self.baseline_btc
        
        diff = abs(actual_delta - expected_delta)
        
        # Tolerancia para comisiones externas o dust
        tolerance = Decimal(str(Config.MIN_BTC_TO_SELL))
        if diff > tolerance:
            logger.critical("INCONSISTENCIA: Esperado Delta %.8f, Real Delta %.8f | Diff: %.8f", expected_delta, actual_delta, diff)
            self.enter_safe_mode("Inconsistencia detectada fuera de tolerancia (Delta Reconciliacion)")

    @property
    def average_buy_price(self) -> Decimal:
        if self.active_btc > 0:
            return self.active_cost_usdt / self.active_btc
        return Decimal("0.0")

    def to_dict(self) -> dict:
        snap = StateSnapshot(
            state=self.state.value,
            state_since=self.state_since,
            last_operation_ts=self.last_operation_ts,
            buy_level_1_done=self.buy_level_1_done,
            buy_level_2_done=self.buy_level_2_done,
            usdt_idle_since=self.usdt_idle_since,
            active_cost_usdt=str(self.active_cost_usdt),
            active_btc=str(self.active_btc),
            accumulated_btc=str(self.accumulated_btc),
            baseline_btc=str(self.baseline_btc) if self.baseline_btc is not None else None
        )
        payload = asdict(snap)
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
        
        machine.active_cost_usdt = Decimal(payload.get("active_cost_usdt", "0.0"))
        machine.active_btc = Decimal(payload.get("active_btc", "0.0"))
        machine.accumulated_btc = Decimal(payload.get("accumulated_btc", "0.0"))
        
        base = payload.get("baseline_btc")
        machine.baseline_btc = Decimal(base) if base is not None else None
        
        machine.history = list(payload.get("history", []))
        return machine
