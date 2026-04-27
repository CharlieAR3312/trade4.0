from __future__ import annotations
import logging
from bitcoin_bot.config import Config
from bitcoin_bot.core.state_machine import BotState

logger = logging.getLogger(__name__)

class DecisionEngine:
    def __init__(self, market_client, price_engine, state_machine, base_calculator, volatility_engine, order_manager, validator, fee_calculator, exposure_limiter, bull_protection, trade_log, state_store, notifier=None):
        self.market_client = market_client
        self.price_engine = price_engine
        self.state_machine = state_machine
        self.base_calculator = base_calculator
        self.volatility_engine = volatility_engine
        self.order_manager = order_manager
        self.validator = validator
        self.fee_calculator = fee_calculator
        self.exposure_limiter = exposure_limiter
        self.bull_protection = bull_protection
        self.trade_log = trade_log
        self.state_store = state_store
        self.notifier = notifier

    def on_price_tick(self, price_engine) -> None:
        if not self.state_machine.is_safe() or not price_engine.is_fresh():
            return
        
        self.volatility_engine.update()
            
        current_price = price_engine.current_price
        if current_price is None:
            return
            
        self.base_calculator.initialize(current_price)
        base_price = self.base_calculator.base_price
        
        # We now track average_buy_price as our true break-even
        avg_price = self.state_machine.average_buy_price
        
        # Calculate change from base (only for trailing stop reference)
        change_from_base = price_engine.get_change_from_base(base_price)
        
        # Calculate change from average buy price (actual profit)
        profit_margin = 0.0
        if avg_price > 0:
            profit_margin = (current_price - avg_price) / avg_price
            
        current_rsi = self.volatility_engine.current_rsi
        
        logger.info(f"Precio: {current_price:.2f} | Avg: {avg_price:.2f} | Profit: {profit_margin*100:.2f}% | RSI: {current_rsi:.1f} | Estado: {self.state_machine.state.value}")
        
        if self.state_machine.is_cooling_down():
            self._persist()
            return

        rsi_oversold = getattr(Config, "RSI_OVERSOLD", 30)
        rsi_overbought = getattr(Config, "RSI_OVERBOUGHT", 70)

        # SELL CONDITION:
        # Must be profitable AND (RSI is overbought OR Trailing Stop triggered from peak)
        is_profitable_trade = self.fee_calculator.is_profitable(profit_margin) if avg_price > 0 else False
        drop_from_peak = abs(self.price_engine.get_drop_from_peak())
        trailing_triggered = drop_from_peak >= Config.TRAILING_STOP_PCT and change_from_base > 0
        
        if self.state_machine.total_usdt_invested > 0 and is_profitable_trade:
            if current_rsi >= rsi_overbought or trailing_triggered:
                self._handle_sell_path(profit_margin)
            else:
                # Update peak for trailing stop
                self.price_engine.reset_peak(base_price if base_price > current_price else current_price)
        else:
            self.price_engine.reset_peak(current_price)

        # BUY CONDITION:
        # RSI is oversold AND we haven't completed all buys
        # We also check if price dropped relative to the local peak to catch the bottom
        if current_rsi <= rsi_oversold:
            self._handle_buy_path(abs(change_from_base))
        elif self.state_machine.state == BotState.EN_BAJADA:
            self.state_machine.transition(BotState.NEUTRO, "RSI salio de zona de sobreventa")
            
        self._handle_forced_buy()
        self._persist()

    def _handle_sell_path(self, profit_margin: float) -> None:
        if self.state_machine.state != BotState.EN_SUBIDA:
            self.state_machine.transition(BotState.EN_SUBIDA, "Condiciones de venta (RSI/Trailing) cumplidas con profit")
            
        snapshot = self.market_client.get_portfolio_snapshot(Config.SYMBOL)
        if snapshot is None:
            return
            
        usdt_to_recover = self.state_machine.total_usdt_invested
        if usdt_to_recover <= 0:
            return

        current_price = self.price_engine.current_price
        
        # SPLIT LOGIC 50/50
        # Calculate gross value of our total BTC position
        total_btc = self.state_machine.total_btc_bought
        gross_value = total_btc * current_price
        
        # Net profit in USDT
        net_profit_usdt = gross_value - usdt_to_recover - (gross_value * Config.BINANCE_FEE_PCT)
        
        split_pct = getattr(Config, "PROFIT_SPLIT_USDT_PCT", 0.5)
        
        # We want to sell enough BTC to get our initial USDT back + split_pct of the profit
        target_usdt_to_receive = usdt_to_recover + (net_profit_usdt * split_pct)
        
        sell_qty = target_usdt_to_receive / current_price
        
        # Exposure limiter handles max limits and decimals
        sell_qty = self.exposure_limiter.sell_quantity(snapshot["btc_balance"], current_price, target_usdt_to_receive)
        
        if sell_qty < Config.MIN_BTC_TO_SELL:
            logger.info("Cantidad a vender es menor al minimo de exchange. Ignorando.")
            return
            
        validation = self.validator.validate_sell(sell_qty, current_price)
        if not validation["ok"]:
            return
            
        execution = self.order_manager.market_sell(validation["quantity"])
        if execution is None:
            self.state_machine.enter_safe_mode("Fallo una venta")
            if self.notifier: self.notifier.notify_safe_mode("Fallo una venta")
            return
            
        self.trade_log.append(execution)
        if self.notifier: self.notifier.notify_sell(execution)
        
        # Register partial sell (or full if we sold almost everything)
        self.state_machine.register_sell(btc_sold=execution.get("quantity", sell_qty), full_sell=False)
        self.state_machine.register_usdt_received()
        
        # Reset base price for next cycles
        self.base_calculator.update(execution["price"], "post_sell")
        self.price_engine.reset_peak(execution["price"])

    def _handle_buy_path(self, drop_ratio: float) -> None:
        if self.state_machine.state != BotState.EN_BAJADA:
            self.state_machine.transition(BotState.EN_BAJADA, "RSI en sobreventa")
        snapshot = self.market_client.get_portfolio_snapshot(Config.SYMBOL)
        if snapshot is None:
            return
            
        # Instead of strict drop ratio, we use RSI. But we keep levels for scaling in.
        if not self.state_machine.buy_level_1_done:
            self._execute_buy_level(1, Config.BUY_LEVEL_1_USDT_PCT, snapshot["usdt_balance"])
            return
            
        if not self.state_machine.buy_level_2_done and self.volatility_engine.current_rsi < getattr(Config, "RSI_OVERSOLD", 30) - 5:
            # Only buy level 2 if RSI drops even lower
            self._execute_buy_level(2, Config.BUY_LEVEL_2_USDT_PCT, snapshot["usdt_balance"])

    def _execute_buy_level(self, level: int, fraction: float, usdt_balance: float) -> None:
        validation = self.validator.validate_buy(usdt_balance * fraction)
        if not validation["ok"]:
            return
        execution = self.order_manager.market_buy(validation["quote_amount"])
        if execution is None:
            self.state_machine.enter_safe_mode(f"Fallo compra nivel {level}")
            if self.notifier: self.notifier.notify_safe_mode(f"Fallo compra nivel {level}")
            return
        self.trade_log.append(execution)
        if self.notifier: self.notifier.notify_buy(execution, level)
        
        usdt_spent = execution.get("quote_amount", validation["quote_amount"])
        btc_bought = execution.get("quantity", 0.0)
        price = execution.get("price", self.price_engine.current_price)
        
        self.state_machine.register_buy(level, usdt_spent, btc_bought, price)
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
            if self.notifier: self.notifier.notify_safe_mode("Fallo compra forzada")
            return
        execution["reason"] = plan["reason"]
        self.trade_log.append(execution)
        if self.notifier: self.notifier.notify_buy(execution, 2)
        
        usdt_spent = execution.get("quote_amount", validation["quote_amount"])
        btc_bought = execution.get("quantity", 0.0)
        price = execution.get("price", self.price_engine.current_price)
        
        self.state_machine.register_buy(2, usdt_spent, btc_bought, price)
        self.state_machine.register_usdt_spent()

    def _persist(self) -> None:
        self.state_store.save({"base": self.base_calculator.to_dict(), "state_machine": self.state_machine.to_dict(), "last_price": self.price_engine.current_price, "peak_price": self.price_engine.peak_price})
