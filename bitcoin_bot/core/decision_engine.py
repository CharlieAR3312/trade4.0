from __future__ import annotations
import logging
from decimal import Decimal
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
            
        # Snapshot para reconciliacion
        snapshot = self.market_client.get_portfolio_snapshot(Config.SYMBOL)
        if snapshot is None:
            return
            
        # Reconciliacion por Delta
        self.state_machine.check_reconciliation(snapshot["btc_balance"])
        if not self.state_machine.is_safe():
            self._persist()
            return
            
        self.base_calculator.initialize(current_price)
        
        avg_price = self.state_machine.average_buy_price
        profit_margin = Decimal("0.0")
        if avg_price > 0:
            profit_margin = (current_price - avg_price) / avg_price
            
        current_rsi = self.volatility_engine.current_rsi
        current_atr = getattr(self.volatility_engine, "current_atr", Decimal("0.0")) or Decimal("0.0")
        
        logger.info(f"Precio: {current_price:.2f} | Avg: {avg_price:.2f} | Profit: {profit_margin*100:.2f}% | RSI: {current_rsi:.1f} | Estado: {self.state_machine.state.value}")
        
        rsi_oversold = Decimal(str(Config.RSI_OVERSOLD))
        rsi_overbought = Decimal(str(Config.RSI_OVERBOUGHT))
        
        # Stop Loss Dinamico (ATR)
        stop_loss_pct = Decimal("0.02")
        if current_atr > 0:
            stop_loss_pct = (current_atr * Config.STOP_LOSS_ATR_MULTIPLIER) / current_price
            
        # Limites de SL (0.5% - 3%)
        stop_loss_pct = max(Decimal("0.005"), min(Decimal("0.03"), stop_loss_pct))
        
        # Peak Tracking para Trailing Stop
        if profit_margin > 0:
            self.price_engine.reset_peak(max(self.price_engine.peak_price, current_price))
        else:
            self.price_engine.reset_peak(current_price)
            
        drop_from_peak = abs(self.price_engine.get_drop_from_peak())
        trailing_triggered = drop_from_peak >= Config.TRAILING_STOP_PCT and profit_margin > 0

        # El stop loss nunca debe quedar bloqueado por cooldown.
        if self.state_machine.active_btc > 0:
            stop_loss_triggered = profit_margin <= -stop_loss_pct
            if stop_loss_triggered:
                logger.warning(f"STOP LOSS ACTIVADO: Perdida {profit_margin*100:.2f}% supero limite de {stop_loss_pct*100:.2f}%")
                self._handle_sell_path(snapshot, True) 
                self._persist()
                return

        if self.state_machine.is_cooling_down():
            self._persist()
            return

        # CONDICIONES DE VENTA
        if self.state_machine.active_btc > 0:
            is_profitable = self.fee_calculator.is_profitable(profit_margin) if avg_price > 0 else False
            if is_profitable and (current_rsi >= rsi_overbought or trailing_triggered):
                self._handle_sell_path(snapshot, False) 
                
        # CONDICIONES DE COMPRA
        if current_rsi <= rsi_oversold and not self.state_machine.buy_level_1_done:
            self._execute_buy_level(1, snapshot["usdt_balance"], stop_loss_pct)
        elif current_rsi <= rsi_oversold - 5 and not self.state_machine.buy_level_2_done and self.state_machine.buy_level_1_done:
            self._execute_buy_level(2, snapshot["usdt_balance"], stop_loss_pct)
        elif self.state_machine.state == BotState.EN_BAJADA and current_rsi > rsi_oversold:
            self.state_machine.transition(BotState.NEUTRO, "RSI salio de zona de sobreventa")
            
        self._persist()

    def _handle_sell_path(self, snapshot: dict, is_stop_loss: bool) -> None:
        if self.state_machine.state != BotState.EN_SUBIDA and not is_stop_loss:
            self.state_machine.transition(BotState.EN_SUBIDA, "Iniciando proceso de venta")
            
        active_cost = self.state_machine.active_cost_usdt
        if active_cost <= 0 and not is_stop_loss:
            # Si no hay capital activo y no es stop loss, no hay nada que vender aqui 
            # (El BTC acumulado se gestiona aparte)
            return

        current_price = self.price_engine.current_price
        active_btc = self.state_machine.active_btc
        
        if is_stop_loss:
            # Stop loss vende TODO el BTC activo
            sell_qty = active_btc
        else:
            # Profit Split: Recuperar capital + porcentaje de ganancia
            gross_value = active_btc * current_price
            net_profit_usdt = gross_value - active_cost - (gross_value * Config.BINANCE_FEE_PCT)
            
            target_usdt_to_receive = active_cost + (max(Decimal("0.0"), net_profit_usdt) * Config.PROFIT_SPLIT_USDT_PCT)
            sell_qty = target_usdt_to_receive / current_price
        
        # Validacion de cantidad
        if sell_qty < Config.MIN_BTC_TO_SELL:
            return
            
        validation = self.validator.validate_sell(sell_qty, current_price)
        if not validation["ok"]:
            return
            
        execution = self.order_manager.market_sell(validation["quantity"])
        if execution is None:
            self.state_machine.enter_safe_mode("Fallo critico en ejecucion de venta")
            if self.notifier: self.notifier.notify_safe_mode("Fallo una venta")
            return
            
        # Log y Notificacion
        exec_dict = {
            "order_id": execution.order_id, "client_order_id": execution.client_order_id,
            "status": execution.status, "side": execution.side, "symbol": execution.symbol,
            "price": str(execution.avg_price), "quantity": str(execution.executed_qty),
            "quote_amount": str(execution.quote_qty), "fee_paid": str(execution.fee_in_usdt),
            "fee_qty": str(execution.fee_qty), "fee_asset": execution.fee_asset,
            "fee_in_usdt": str(execution.fee_in_usdt), "timestamp": execution.timestamp
        }
        self.trade_log.append(exec_dict)
        if self.notifier: self.notifier.notify_sell(exec_dict)
        
        partial_or_unfilled = execution.status != "FILLED"
        # Registro contable
        self.state_machine.register_sell(
            btc_sold=execution.executed_qty, 
            quote_received=execution.quote_qty, 
            full_sell=is_stop_loss and not partial_or_unfilled
        )
        if partial_or_unfilled:
            self.state_machine.enter_safe_mode(f"Orden de venta no finalizada ({execution.status}). Reconciliacion manual requerida.")
            if self.notifier: self.notifier.notify_safe_mode(f"Venta {execution.status}")
            self._persist()
            return
        
        if not is_stop_loss:
            self.state_machine.register_usdt_received()
        
        self.base_calculator.update(execution.avg_price, "post_sell")
        self.price_engine.reset_peak(execution.avg_price)

    def _execute_buy_level(self, level: int, usdt_balance: Decimal, stop_loss_pct: Decimal) -> None:
        if self.state_machine.state != BotState.EN_BAJADA:
            self.state_machine.transition(BotState.EN_BAJADA, "Detectada oportunidad de compra")
            
        # Position Sizing con riesgo controlado
        max_loss_usdt = usdt_balance * Config.RISK_PER_TRADE_PCT
        target_quote = max_loss_usdt / stop_loss_pct if stop_loss_pct > 0 else Decimal("0.0")
        
        # Limite por nivel
        max_allowed_quote = usdt_balance * (Config.BUY_LEVEL_1_USDT_PCT if level == 1 else Config.BUY_LEVEL_2_USDT_PCT)
        if target_quote == 0 or target_quote > max_allowed_quote:
            target_quote = max_allowed_quote
            
        validation = self.validator.validate_buy(target_quote)
        if not validation["ok"]:
            return
            
        execution = self.order_manager.market_buy(validation["quote_amount"])
        if execution is None:
            self.state_machine.enter_safe_mode(f"Fallo compra nivel {level}")
            if self.notifier: self.notifier.notify_safe_mode(f"Fallo compra nivel {level}")
            return
            
        exec_dict = {
            "order_id": execution.order_id, "client_order_id": execution.client_order_id,
            "status": execution.status, "side": execution.side, "symbol": execution.symbol,
            "price": str(execution.avg_price), "quantity": str(execution.executed_qty),
            "quote_amount": str(execution.quote_qty), "fee_paid": str(execution.fee_in_usdt),
            "fee_qty": str(execution.fee_qty), "fee_asset": execution.fee_asset,
            "fee_in_usdt": str(execution.fee_in_usdt), "timestamp": execution.timestamp
        }
        self.trade_log.append(exec_dict)
        if self.notifier: self.notifier.notify_buy(exec_dict, level)
        
        self.state_machine.register_buy(level, execution.quote_qty, execution.executed_qty)
        if execution.status != "FILLED":
            self.state_machine.enter_safe_mode(f"Orden de compra no finalizada ({execution.status}). Reconciliacion manual requerida.")
            if self.notifier: self.notifier.notify_safe_mode(f"Compra {execution.status}")
            self._persist()
            return
        self.state_machine.register_usdt_spent()
        self.price_engine.reset_peak(execution.avg_price)

    def _persist(self) -> None:
        self.state_store.save({
            "base": self.base_calculator.to_dict(), 
            "state_machine": self.state_machine.to_dict(), 
            "last_price": str(self.price_engine.current_price) if self.price_engine.current_price else "0.0", 
            "peak_price": str(self.price_engine.peak_price) if self.price_engine.peak_price else "0.0"
        })
