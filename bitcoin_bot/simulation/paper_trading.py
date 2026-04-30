from __future__ import annotations
import logging
import time
import uuid
import random
from decimal import Decimal
from bitcoin_bot.config import Config
from bitcoin_bot.core.models import OrderExecution

logger = logging.getLogger(__name__)

class PaperBinanceClient:
    """
    Simulador de Binance con dos modos:
    
    1. OFFLINE (--demo): Genera precios sintéticos. No necesita API Keys.
    2. LIVE PAPER (paper + API Keys): Lee datos reales de Binance (precios, RSI, 
       balances iniciales) pero simula las órdenes sin ejecutarlas.
    """
    def __init__(self, initial_btc: str = "0.0", initial_usdt: str = "0.0", live_reader=None):
        self._live = live_reader  # BinanceClient real (solo lectura)
        
        # Si tenemos conexión real, leemos los balances actuales de la cuenta
        if self._live:
            try:
                real_btc = self._live.get_balance("BTC")
                real_usdt = self._live.get_balance("USDT")
                real_price = self._live.get_price(Config.SYMBOL)
                
                self.balances = {
                    "BTC": real_btc,
                    "USDT": real_usdt
                }
                self.current_price = real_price or Decimal("95000.0")
                
                logger.info("📡 PAPER LIVE: Balances reales cargados -> %.8f BTC | %.2f USDT | Precio: $%.2f",
                    float(real_btc), float(real_usdt), float(self.current_price))
            except Exception as exc:
                logger.error("Error leyendo balances reales, usando defaults: %s", exc)
                self.balances = {"BTC": Decimal(initial_btc), "USDT": Decimal(initial_usdt)}
                self.current_price = Decimal("95000.0")
        else:
            self.balances = {
                "BTC": Decimal(initial_btc),
                "USDT": Decimal(initial_usdt)
            }
            self.current_price = Decimal("95000.0")
        
        # Guardar balances iniciales para el log final
        self._initial_balances = dict(self.balances)
        
        self.symbol_info = {
            "min_qty": Config.MIN_BTC_TO_SELL,
            "step_size": Config.MIN_BTC_TO_SELL,
            "min_notional": Config.MIN_USDT_TO_OPERATE
        }

    def reconnect(self) -> None:
        if self._live:
            self._live.reconnect()

    def get_price(self, symbol: str) -> Decimal:
        if self._live:
            try:
                price = self._live.get_price(symbol)
                if price and price > 0:
                    self.current_price = price
            except Exception as exc:
                logger.warning("Error leyendo precio real, usando último conocido: %s", exc)
        return self.current_price

    def set_price(self, price: Decimal | float) -> None:
        self.current_price = Decimal(str(price))

    def get_balance(self, asset: str) -> Decimal:
        return self.balances.get(asset, Decimal("0.0"))

    def get_portfolio_snapshot(self, symbol: str) -> dict:
        # Actualizar precio antes del snapshot
        self.get_price(symbol)
        btc_value_usdt = self.balances["BTC"] * self.current_price
        return {
            "btc_balance": self.balances["BTC"],
            "usdt_balance": self.balances["USDT"],
            "btc_price": self.current_price,
            "btc_value_usdt": btc_value_usdt,
            "total_usdt": btc_value_usdt + self.balances["USDT"],
            "timestamp": time.time()
        }

    def get_symbol_info(self, symbol: str) -> dict:
        if self._live:
            try:
                info = self._live.get_symbol_info(symbol)
                if info:
                    return info
            except Exception:
                pass
        return self.symbol_info

    def get_klines(self, symbol: str, interval: str, limit: int = 14) -> list:
        if self._live:
            try:
                klines = self._live.get_klines(symbol, interval, limit)
                if klines:
                    return klines
            except Exception as exc:
                logger.warning("Error leyendo klines reales: %s", exc)
            
        # Fallback: Mock klines offline
        klines = []
        now = int(time.time() * 1000)
        base = self.current_price
        for i in range(limit):
            var = Decimal(str(random.uniform(-0.01, 0.01)))
            close_p = base * (Decimal("1") + var)
            klines.append([
                now - (limit - i) * 3600000,
                str(base), str(max(base, close_p) * Decimal("1.001")), 
                str(min(base, close_p) * Decimal("0.999")), str(close_p), "0"
            ])
            base = close_p
        return klines

    def get_order_status(self, symbol: str, client_order_id: str) -> OrderExecution | None:
        return None

    def create_market_buy(self, symbol: str, quote_amount: Decimal | float, client_order_id: str = "") -> OrderExecution:
        quote_amount = Decimal(str(quote_amount))
        if quote_amount > self.balances["USDT"]:
            raise RuntimeError("USDT insuficiente en paper trading")
            
        fee_paid = quote_amount * Config.BINANCE_FEE_PCT
        quantity = (quote_amount - fee_paid) / self.current_price
        
        self.balances["USDT"] -= quote_amount
        self.balances["BTC"] += quantity
        
        logger.info("📝 PAPER BUY %.2f USDT -> %.8f BTC a $%.2f", quote_amount, quantity, self.current_price)
        
        return OrderExecution(
            order_id=str(uuid.uuid4()),
            client_order_id=client_order_id,
            side="BUY",
            symbol=symbol,
            status="FILLED",
            executed_qty=quantity,
            quote_qty=quote_amount,
            avg_price=self.current_price,
            fee_qty=fee_paid,
            fee_asset="USDT",
            fee_in_usdt=fee_paid,
            timestamp=time.time()
        )

    def create_market_sell(self, symbol: str, quantity: Decimal | float, client_order_id: str = "") -> OrderExecution:
        quantity = Decimal(str(quantity))
        if quantity > self.balances["BTC"]:
            raise RuntimeError("BTC insuficiente en paper trading")
            
        gross_quote = quantity * self.current_price
        fee_paid = gross_quote * Config.BINANCE_FEE_PCT
        net_quote = gross_quote - fee_paid
        
        self.balances["BTC"] -= quantity
        self.balances["USDT"] += net_quote
        
        logger.info("📝 PAPER SELL %.8f BTC -> %.2f USDT a $%.2f", quantity, net_quote, self.current_price)
        
        return OrderExecution(
            order_id=str(uuid.uuid4()),
            client_order_id=client_order_id,
            side="SELL",
            symbol=symbol,
            status="FILLED",
            executed_qty=quantity,
            quote_qty=net_quote,
            avg_price=self.current_price,
            fee_qty=fee_paid,
            fee_asset="USDT",
            fee_in_usdt=fee_paid,
            timestamp=time.time()
        )

    def print_summary(self) -> None:
        """Imprime un resumen de la simulación comparando el estado inicial vs actual."""
        init_btc = self._initial_balances.get("BTC", Decimal("0"))
        init_usdt = self._initial_balances.get("USDT", Decimal("0"))
        init_total = init_btc * self.current_price + init_usdt
        
        curr_btc = self.balances["BTC"]
        curr_usdt = self.balances["USDT"]
        curr_total = curr_btc * self.current_price + curr_usdt
        
        delta = curr_total - init_total
        pct = (delta / init_total * Decimal("100")) if init_total > 0 else Decimal("0")
        
        logger.info("=" * 50)
        logger.info("📊 RESUMEN DE SIMULACION PAPER")
        logger.info("=" * 50)
        logger.info("INICIO  -> BTC: %.8f | USDT: %.2f | Total: $%.2f", float(init_btc), float(init_usdt), float(init_total))
        logger.info("ACTUAL  -> BTC: %.8f | USDT: %.2f | Total: $%.2f", float(curr_btc), float(curr_usdt), float(curr_total))
        logger.info("DELTA   -> $%.2f (%+.2f%%)", float(delta), float(pct))
        logger.info("=" * 50)
