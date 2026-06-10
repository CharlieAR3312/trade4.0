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

        snapshot = self.market_client.get_portfolio_snapshot(Config.SYMBOL)
        if snapshot is None:
            return

        # Reconciliacion por Delta
        self.state_machine.check_reconciliation(snapshot["btc_balance"])
        if not self.state_machine.is_safe():
            self._persist()
            return

        self.base_calculator.initialize(current_price)

        # ─── AUTO-LIMPIEZA DE DUST ───────────────────────────────────────────
        if self.state_machine.active_btc > 0:
            is_dust_btc = self.state_machine.active_btc < Config.MIN_BTC_TO_SELL
            is_dust_usdt = self.state_machine.active_cost_usdt < Config.MIN_USDT_TO_OPERATE
            if is_dust_btc or is_dust_usdt:
                logger.warning(f"Limpiando dust residual: {self.state_machine.active_btc} BTC")
                self.state_machine.accumulated_btc += self.state_machine.active_btc
                self.state_machine.active_btc = Decimal("0.0")
                self.state_machine.active_cost_usdt = Decimal("0.0")
                self.state_machine.buy_level_1_done = False
                self.state_machine.buy_level_2_done = False
                if self.state_machine.state not in (BotState.VENDIDO,):
                    self.state_machine.transition(BotState.NEUTRO, "Dust limpiado")
                self._persist()
                return

        has_position = self.state_machine.active_btc > 0
        usdt_balance = snapshot["usdt_balance"]
        avg_price = self.state_machine.average_buy_price
        profit_margin = Decimal("0.0")
        if avg_price > 0:
            profit_margin = (current_price - avg_price) / avg_price

        current_rsi = self.volatility_engine.current_rsi
        current_atr = getattr(self.volatility_engine, "current_atr", Decimal("0.0")) or Decimal("0.0")

        # Trailing trackers
        if price_engine.peak_price is None or current_price > price_engine.peak_price:
            price_engine.reset_peak(current_price)
        if price_engine.valley_price is None or current_price < price_engine.valley_price:
            price_engine.reset_valley(current_price)

        drop_from_peak = abs(price_engine.get_drop_from_peak())
        rise_from_valley = abs(price_engine.get_rise_from_valley())

        trailing_triggered = (
            has_position
            and drop_from_peak >= Config.TRAILING_STOP_PCT
            and profit_margin > 0
        )

        logger.info(
            f"Precio: {current_price:.2f} | RSI: {current_rsi:.1f} | "
            f"Caida: {drop_from_peak*100:.2f}% | Subida: {rise_from_valley*100:.2f}% | "
            f"Profit: {profit_margin*100:.3f}% | Estado: {self.state_machine.state.value} | "
            f"BTC: {self.state_machine.active_btc:.6f} | USDT: {usdt_balance:.2f}"
        )

        # ─── STOP LOSS DINAMICO (ATR) ────────────────────────────────────────
        stop_loss_pct = Decimal("0.02")
        if current_atr > 0:
            stop_loss_pct = (current_atr * Config.STOP_LOSS_ATR_MULTIPLIER) / current_price
        stop_loss_pct = max(Decimal("0.005"), min(Decimal("0.03"), stop_loss_pct))

        if has_position and profit_margin <= -stop_loss_pct:
            logger.warning(f"STOP LOSS: {profit_margin*100:.2f}% | Limite: {stop_loss_pct*100:.2f}%")
            self._handle_sell_path(snapshot, is_stop_loss=True)
            self._persist()
            return

        if self.state_machine.is_cooling_down():
            self._persist()
            return

        # ═══════════════════════════════════════════════════════════════════
        # CEREBRO DE TRADING v2.5
        # Tres modos: A) BTC en mano, B) VENDIDO esperando fondo, C) NEUTRO
        # ═══════════════════════════════════════════════════════════════════

        # ─── MODO A: Tengo BTC — vender con profit O vender defensivamente ───
        if has_position:
            is_profitable = profit_margin >= Config.BASE_SELL_THRESHOLD_PCT
            rsi_overbought = current_rsi >= Config.RSI_OVERBOUGHT

            # A1) VENTA CON PROFIT (objetivo principal del ciclo)
            if is_profitable or trailing_triggered or (is_profitable and rsi_overbought):
                logger.info(f"VENTA CON PROFIT: {profit_margin*100:.3f}%")
                self._handle_sell_path(snapshot, is_stop_loss=False)
                self._persist()
                return

            # A2) VENTA DEFENSIVA: El mercado empieza a caer fuerte
            # Vende TODO el BTC ahora para recomprar mucho mas abajo
            # Condicion: caida >= 1.2% desde pico Y RSI aun alto (mercado no en sobreventa)
            # Esto significa que la caida recien comienza y hay mas para bajar
            defensive_conditions = (
                drop_from_peak >= Config.DEFENSIVE_SELL_THRESHOLD_PCT
                and current_rsi > Config.DEFENSIVE_RSI_MAX
                and profit_margin > Decimal("-0.008")  # No vender si ya perdimos mas del 0.8%
            )
            if defensive_conditions:
                logger.warning(
                    f"VENTA DEFENSIVA: caida {drop_from_peak*100:.2f}% | "
                    f"RSI {current_rsi:.1f} | Convirtiendo BTC a USDT"
                )
                self._handle_defensive_sell(snapshot, current_price)
                self._persist()
                return

        # ─── MODO B: VENDIDO — esperar fondo y recomprar ────────────────────
        elif self.state_machine.state == BotState.VENDIDO:
            # Recompra cuando detecta rebote >= 1.0% desde el valle Y RSI sale de sobreventa
            reentry_conditions = (
                rise_from_valley >= Config.REENTRY_RISE_PCT
                and current_rsi > Config.REENTRY_RSI_MIN
                and usdt_balance >= Config.MIN_USDT_TO_OPERATE
            )
            if reentry_conditions:
                dsp = self.state_machine.defensive_sell_price or current_price
                logger.info(
                    f"RECOMPRA INTELIGENTE: rebote {rise_from_valley*100:.2f}% desde valle | "
                    f"RSI {current_rsi:.1f} | Vendimos a ${float(dsp):,.2f}"
                )
                self._execute_buy_level(1, usdt_balance, stop_loss_pct, reentry=True)
                self._persist()
                return

        # ─── MODO C: NEUTRO con USDT — scalping normal ──────────────────────
        elif not has_position and usdt_balance >= Config.MIN_USDT_TO_OPERATE:
            condicion_caida = (
                drop_from_peak >= Config.BASE_BUY_LEVEL_1_PCT
                and current_rsi < Config.RSI_OVERSOLD
            )
            condicion_momentum = (rise_from_valley >= Config.MOMENTUM_BUY_PCT)

            if condicion_caida or condicion_momentum:
                self._execute_buy_level(1, usdt_balance, stop_loss_pct)
            elif (has_position
                    and not self.state_machine.buy_level_2_done
                    and drop_from_peak >= Config.BASE_BUY_LEVEL_1_PCT + Config.BASE_BUY_LEVEL_2_PCT
                    and current_rsi < 50):
                self._execute_buy_level(2, usdt_balance, stop_loss_pct)

        self._persist()

    def _handle_defensive_sell(self, snapshot: dict, current_price: Decimal) -> None:
        """Vende todo el BTC para convertirlo a USDT antes de que el mercado caiga mas."""
        active_btc = self.state_machine.active_btc
        if active_btc < Config.MIN_BTC_TO_SELL:
            return

        validation = self.validator.validate_sell(active_btc, current_price)
        if not validation["ok"]:
            return

        execution = self.order_manager.market_sell(validation["quantity"])
        if execution is None:
            self.state_machine.enter_safe_mode("Fallo en venta defensiva")
            if self.notifier:
                self.notifier.notify_safe_mode("Fallo venta defensiva")
            return

        exec_dict = {
            "order_id": execution.order_id, "client_order_id": execution.client_order_id,
            "status": "DEFENSIVE_SELL", "side": "SELL", "symbol": execution.symbol,
            "price": str(execution.avg_price), "quantity": str(execution.executed_qty),
            "quote_amount": str(execution.quote_qty), "fee_paid": str(execution.fee_in_usdt),
            "fee_qty": str(execution.fee_qty), "fee_asset": execution.fee_asset,
            "fee_in_usdt": str(execution.fee_in_usdt), "timestamp": execution.timestamp
        }
        self.trade_log.append(exec_dict)

        if self.notifier:
            self.notifier.send(
                f"🛡️ *VENTA DEFENSIVA EJECUTADA*\n"
                f"Vendí `{float(execution.executed_qty):.6f}` BTC a `${float(execution.avg_price):,.2f}`\n"
                f"💵 USDT en caja: `${float(execution.quote_qty):,.2f}`\n"
                f"⏳ Esperando el fondo para recomprar más barato..."
            )

        # Actualizar estado: ahora somos VENDIDO, esperando recompra
        self.state_machine.defensive_sell_price = execution.avg_price
        self.state_machine.active_btc = Decimal("0.0")
        self.state_machine.active_cost_usdt = Decimal("0.0")
        self.state_machine.buy_level_1_done = False
        self.state_machine.buy_level_2_done = False
        self.state_machine.transition(BotState.VENDIDO, f"Venta defensiva a ${float(execution.avg_price):,.2f}")
        self.state_machine.register_usdt_received()
        self.price_engine.reset_valley(execution.avg_price)

    def _handle_sell_path(self, snapshot: dict, is_stop_loss: bool) -> None:
        if self.state_machine.state != BotState.EN_SUBIDA and not is_stop_loss:
            self.state_machine.transition(BotState.EN_SUBIDA, "Iniciando proceso de venta")

        active_cost = self.state_machine.active_cost_usdt
        if active_cost <= 0 and not is_stop_loss:
            return

        current_price = self.price_engine.current_price
        active_btc = self.state_machine.active_btc

        if is_stop_loss:
            sell_qty = active_btc
        else:
            gross_value = active_btc * current_price
            net_profit_usdt = gross_value - active_cost - (gross_value * Config.BINANCE_FEE_PCT)
            target_usdt_to_receive = active_cost + (max(Decimal("0.0"), net_profit_usdt) * Config.PROFIT_SPLIT_USDT_PCT)
            sell_qty = target_usdt_to_receive / current_price

        if sell_qty < Config.MIN_BTC_TO_SELL:
            return

        validation = self.validator.validate_sell(sell_qty, current_price)
        if not validation["ok"]:
            return

        execution = self.order_manager.market_sell(validation["quantity"])
        if execution is None:
            self.state_machine.enter_safe_mode("Fallo critico en ejecucion de venta")
            if self.notifier:
                self.notifier.notify_safe_mode("Fallo una venta")
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
        if self.notifier:
            self.notifier.notify_sell(exec_dict)

        partial_or_unfilled = execution.status != "FILLED"
        self.state_machine.register_sell(
            btc_sold=execution.executed_qty,
            quote_received=execution.quote_qty,
            full_sell=is_stop_loss and not partial_or_unfilled
        )
        if partial_or_unfilled:
            self.state_machine.enter_safe_mode(
                f"Orden de venta no finalizada ({execution.status}). Reconciliacion manual requerida."
            )
            if self.notifier:
                self.notifier.notify_safe_mode(f"Venta {execution.status}")
            self._persist()
            return

        if not is_stop_loss:
            self.state_machine.register_usdt_received()
        self.state_machine.defensive_sell_price = None
        self.base_calculator.update(execution.avg_price, "post_sell")
        self.price_engine.reset_peak(execution.avg_price)
        self.price_engine.reset_valley(execution.avg_price)

    def _execute_buy_level(self, level: int, usdt_balance: Decimal, stop_loss_pct: Decimal, reentry: bool = False) -> None:
        reason = "Recompra post-venta-defensiva" if reentry else f"Oportunidad de compra nivel {level}"
        if self.state_machine.state != BotState.EN_BAJADA:
            self.state_machine.transition(BotState.EN_BAJADA, reason)

        max_loss_usdt = usdt_balance * Config.RISK_PER_TRADE_PCT
        target_quote = max_loss_usdt / stop_loss_pct if stop_loss_pct > 0 else Decimal("0.0")

        max_allowed_quote = usdt_balance * (Config.BUY_LEVEL_1_USDT_PCT if level == 1 else Config.BUY_LEVEL_2_USDT_PCT)
        if target_quote == 0 or target_quote > max_allowed_quote:
            target_quote = max_allowed_quote

        validation = self.validator.validate_buy(target_quote)
        if not validation["ok"]:
            return

        execution = self.order_manager.market_buy(validation["quote_amount"])
        if execution is None:
            self.state_machine.enter_safe_mode(f"Fallo compra nivel {level}")
            if self.notifier:
                self.notifier.notify_safe_mode(f"Fallo compra nivel {level}")
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
        if self.notifier:
            self.notifier.notify_buy(exec_dict, level)

        self.state_machine.register_buy(level, execution.quote_qty, execution.executed_qty)
        self.state_machine.defensive_sell_price = None  # Ciclo completado exitosamente

        if execution.status != "FILLED":
            self.state_machine.enter_safe_mode(
                f"Orden de compra no finalizada ({execution.status}). Reconciliacion manual requerida."
            )
            if self.notifier:
                self.notifier.notify_safe_mode(f"Compra {execution.status}")
            self._persist()
            return

        self.state_machine.register_usdt_spent()
        self.price_engine.reset_peak(execution.avg_price)
        self.price_engine.reset_valley(execution.avg_price)

    def _persist(self) -> None:
        self.state_store.save({
            "base": self.base_calculator.to_dict(),
            "state_machine": self.state_machine.to_dict(),
            "last_price": str(self.price_engine.current_price) if self.price_engine.current_price else "0.0",
            "peak_price": str(self.price_engine.peak_price) if self.price_engine.peak_price else "0.0"
        })
