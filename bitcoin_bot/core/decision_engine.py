from __future__ import annotations
import logging
from bitcoin_bot.config import Config
from bitcoin_bot.core.state_machine import BotState

logger = logging.getLogger(__name__)

class DecisionEngine:
    def __init__(self, market_client, price_engine, state_machine, base_calculator, order_manager, validator, fee_calculator, exposure_limiter, bull_protection, trade_log, state_store):
        self.market_client = market_client
        self.price_engine = price_engine
        self.state_machine = state_machine
        self.base_calculator = base_calculator
        self.order_manager = order_manager
        self.validator = validator
        self.fee_calculator = fee_calculator
        self.exposure_limiter = exposure_limiter
        self.bull_protection = bull_protection
        self.trade_log = trade_log
        self.state_store = state_store

    def on_price_tick(self, price_engine) -> None:
        if not self.state_machine.is_safe() or not price_engine.is_fresh():
            return
        current_price = price_engine.current_price
        if current_price is None:
            return
        self.base_calculator.initialize(current_price)
        base_price = self.base_calculator.base_price
        change_from_base = price_engine.get_change_from_base(base_price)
        logger.info("Base %.2f | Cambio %.3f%% | Estado %s", base_price, change_from_base * 100, self.state_machine.state.value)
        if self.state_machine.is_cooling_down():
            self._persist()
            return
        if change_from_base >= Config.MIN_SELL_THRESHOLD_PCT:
            self._handle_sell_path(change_from_base)
        else:
            self.price_engine.reset_peak(base_price)
        buy_trigger = self.bull_protection.current_buy_threshold(self.state_machine)
        if change_from_base <= -buy_trigger:
            self._handle_buy_path(abs(change_from_base))
        elif self.state_machine.state == BotState.EN_BAJADA:
            self.state_machine.transition(BotState.NEUTRO, "Precio salio de zona de compra")
        self._handle_forced_buy()
        self._persist()

    def _handle_sell_path(self, change_from_base: float) -> None:
        if self.state_machine.state != BotState.EN_SUBIDA:
            self.state_machine.transition(BotState.EN_SUBIDA, "Precio supero umbral minimo de venta")
        if not self.fee_calculator.is_profitable(change_from_base):
            return
        drop_from_peak = abs(self.price_engine.get_drop_from_peak())
        if drop_from_peak < Config.TRAILING_STOP_PCT:
            return
        snapshot = self.market_client.get_portfolio_snapshot(Config.SYMBOL)
        if snapshot is None:
            return
        sell_qty = self.exposure_limiter.sell_quantity(snapshot["btc_balance"])
        validation = self.validator.validate_sell(sell_qty, self.price_engine.current_price)
        if not validation["ok"]:
            return
        execution = self.order_manager.market_sell(validation["quantity"])
        if execution is None:
            self.state_machine.enter_safe_mode("Fallo una venta")
            return
        self.trade_log.append(execution)
        self.state_machine.register_sell()
        self.state_machine.register_usdt_received()
        self.base_calculator.update(execution["price"], "post_sell")
        self.price_engine.reset_peak(execution["price"])

    def _handle_buy_path(self, drop_ratio: float) -> None:
        if self.state_machine.state != BotState.EN_BAJADA:
            self.state_machine.transition(BotState.EN_BAJADA, "Precio entro a zona de compra")
        snapshot = self.market_client.get_portfolio_snapshot(Config.SYMBOL)
        if snapshot is None:
            return
        if not self.state_machine.buy_level_1_done and drop_ratio >= Config.BUY_LEVEL_1_PCT:
            self._execute_buy_level(1, Config.BUY_LEVEL_1_USDT_PCT, snapshot["usdt_balance"])
            return
        if not self.state_machine.buy_level_2_done and drop_ratio >= Config.BUY_LEVEL_2_PCT:
            self._execute_buy_level(2, Config.BUY_LEVEL_2_USDT_PCT, snapshot["usdt_balance"])

    def _execute_buy_level(self, level: int, fraction: float, usdt_balance: float) -> None:
        validation = self.validator.validate_buy(usdt_balance * fraction)
        if not validation["ok"]:
            return
        execution = self.order_manager.market_buy(validation["quote_amount"])
        if execution is None:
            self.state_machine.enter_safe_mode(f"Fallo compra nivel {level}")
            return
        self.trade_log.append(execution)
        self.state_machine.register_buy(level)
        self.state_machine.register_usdt_spent()
        self.price_engine.reset_peak(execution["price"])

    def _handle_forced_buy(self) -> None:
        plan = self.bull_protection.force_buy_plan(self.state_machine)
        if plan is None:
            return
        snapshot = self.market_client.get_portfolio_snapshot(Config.SYMBOL)
        if snapshot is None:
            return
        validation = self.validator.validate_buy(snapshot["usdt_balance"] * plan["fraction"])
        if not validation["ok"]:
            return
        execution = self.order_manager.market_buy(validation["quote_amount"])
        if execution is None:
            self.state_machine.enter_safe_mode("Fallo compra forzada")
            return
        execution["reason"] = plan["reason"]
        self.trade_log.append(execution)
        self.state_machine.register_buy(2)
        self.state_machine.register_usdt_spent()

    def _persist(self) -> None:
        self.state_store.save({"base": self.base_calculator.to_dict(), "state_machine": self.state_machine.to_dict(), "last_price": self.price_engine.current_price, "peak_price": self.price_engine.peak_price})
