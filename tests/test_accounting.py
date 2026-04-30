import pytest
from decimal import Decimal
from bitcoin_bot.core.state_machine import StateMachine, BotState
from bitcoin_bot.core.models import OrderExecution
from bitcoin_bot.core.decision_engine import DecisionEngine
from bitcoin_bot.core.base_calculator import BaseCalculator
from bitcoin_bot.core.price_engine import PriceEngine
from bitcoin_bot.exchange.order_manager import OrderManager
from bitcoin_bot.exchange.validator import Validator
from bitcoin_bot.risk.fee_calculator import FeeCalculator
from bitcoin_bot.risk.exposure_limiter import ExposureLimiter
from bitcoin_bot.risk.bull_protection import BullProtection
from bitcoin_bot.config import Config
from bitcoin_bot.exchange.binance_client import BinanceClient
import time

def test_state_machine_accounting_profit_split():
    """Valida que el BTC de ganancia pase al cubo de acumulados y el costo activo se resetee."""
    sm = StateMachine()
    
    # 1. Compra inicial: 100 USDT -> 0.001 BTC
    sm.register_buy(level=1, usdt_spent=Decimal("100.0"), btc_received=Decimal("0.001"))
    assert sm.active_btc == Decimal("0.001")
    assert sm.active_cost_usdt == Decimal("100.0")
    assert sm.average_buy_price == Decimal("100000.0")

    # 2. Venta parcial (Profit Split): Vendemos para recuperar los 100 USDT + algo de profit
    # Supongamos que el precio subio a 200,000.
    # Queremos recuperar 100 USDT. Eso son 0.0005 BTC.
    # Pero el split dice que vendemos mas para ganar USDT.
    # Digamos que vendemos 0.0006 BTC por 120 USDT.
    sm.register_sell(btc_sold=Decimal("0.0006"), quote_received=Decimal("120.0"), full_sell=False)
    
    # El capital activo deberia ser 0 porque recuperamos los 100.
    assert sm.active_cost_usdt == Decimal("0.0")
    # El BTC que sobro (0.001 - 0.0006 = 0.0004) deberia estar en accumulated_btc
    assert sm.accumulated_btc == Decimal("0.0004")
    assert sm.active_btc == Decimal("0.0")
    assert sm.buy_level_1_done == False

def test_decimal_precision_fees():
    """Valida que las comisiones no causen perdida de precision."""
    order = OrderExecution(
        order_id="1", client_order_id="1", side="BUY", symbol="BTCUSDT",
        status="FILLED", executed_qty="0.00123456", quote_qty="100.55",
        avg_price="81446.02", fee_qty="0.00000123", fee_asset="BTC"
    )
    assert isinstance(order.executed_qty, Decimal)
    assert order.executed_qty == Decimal("0.00123456")
    assert order.fee_qty == Decimal("0.00000123")

def test_reconciliation_delta():
    """Valida que la reconciliacion por delta ignore fondos externos iniciales."""
    sm = StateMachine()
    # Baseline: Cuenta tiene 1.0 BTC externos
    sm.check_reconciliation(real_btc_balance=Decimal("1.0"))
    assert sm.baseline_btc == Decimal("1.0")
    
    # Bot compra 0.1 BTC
    sm.register_buy(level=1, usdt_spent=Decimal("1000"), btc_received=Decimal("0.1"))
    
    # En el exchange ahora hay 1.1 BTC. Esto deberia ser VALIDO.
    sm.check_reconciliation(real_btc_balance=Decimal("1.1"))
    assert sm.state != BotState.MODO_SEGURO
    
    # Si de repente hay 1.05 BTC (alguien vendio 0.05 BTC del bot), deberia entrar en Modo Seguro.
    sm.check_reconciliation(real_btc_balance=Decimal("1.05"))
    assert sm.state == BotState.MODO_SEGURO

def test_state_machine_runtime_methods_exist_and_work():
    sm = StateMachine()
    assert sm.is_safe()
    sm.enter_safe_mode("test")
    assert sm.state == BotState.MODO_SEGURO
    assert not sm.is_safe()

def test_parse_buy_fee_in_btc_uses_net_btc_and_values_fee():
    class FakeClient:
        def get_my_trades(self, symbol, orderId):
            return [{
                "price": "65000.00",
                "qty": "0.01000000",
                "commission": "0.00001000",
                "commissionAsset": "BTC",
            }]

    parser = BinanceClient.__new__(BinanceClient)
    parser.client = FakeClient()
    response = {
        "symbol": "BTCUSDT",
        "orderId": 1,
        "clientOrderId": "abc",
        "side": "BUY",
        "status": "FILLED",
        "executedQty": "0.01000000",
        "cummulativeQuoteQty": "650.00000000",
        "time": 1710000000000,
    }

    order = parser._parse_order_response(response)
    assert order.executed_qty == Decimal("0.00999000")
    assert order.quote_qty == Decimal("650.00000000")
    assert order.fee_asset == "BTC"
    assert order.fee_in_usdt == Decimal("0.6500000000")

def test_parse_bnb_fee_fetches_real_valuation_not_hardcoded():
    class FakeClient:
        def get_symbol_ticker(self, symbol):
            assert symbol == "BNBUSDT"
            return {"price": "700.00"}

    parser = BinanceClient.__new__(BinanceClient)
    parser.client = FakeClient()
    response = {
        "symbol": "BTCUSDT",
        "orderId": 2,
        "clientOrderId": "bnb",
        "side": "BUY",
        "status": "FILLED",
        "executedQty": "0.01000000",
        "cummulativeQuoteQty": "650.00000000",
        "fills": [{
            "price": "65000.00",
            "qty": "0.01000000",
            "commission": "0.001",
            "commissionAsset": "BNB",
        }],
        "time": 1710000000000,
    }

    order = parser._parse_order_response(response)
    assert order.fee_in_usdt == Decimal("0.70000")
    assert order.quote_qty == Decimal("650.70000000")

def test_stop_loss_is_not_blocked_by_cooldown():
    class FakeMarket:
        def __init__(self):
            self.price = Decimal("97000")
            self.sold = Decimal("0")

        def get_price(self, symbol):
            return self.price

        def get_portfolio_snapshot(self, symbol):
            return {
                "btc_balance": Decimal("0.01"),
                "usdt_balance": Decimal("1000"),
                "btc_price": self.price,
                "btc_value_usdt": Decimal("970"),
                "total_usdt": Decimal("1970"),
                "timestamp": time.time(),
            }

        def get_symbol_info(self, symbol):
            return {
                "min_qty": Decimal("0.00001"),
                "step_size": Decimal("0.00001"),
                "min_notional": Decimal("1.50"),
            }

        def get_klines(self, symbol, interval, limit):
            return []

        def get_order_status(self, symbol, client_order_id):
            return None

        def create_market_sell(self, symbol, quantity, client_order_id=""):
            self.sold += Decimal(str(quantity))
            return OrderExecution(
                order_id="sell-1",
                client_order_id=client_order_id,
                side="SELL",
                symbol=symbol,
                status="FILLED",
                executed_qty=quantity,
                quote_qty=Decimal(str(quantity)) * self.price,
                avg_price=self.price,
                fee_qty="0",
                fee_asset="USDT",
                fee_in_usdt="0",
            )

        def create_market_buy(self, symbol, quote_amount, client_order_id=""):
            raise AssertionError("stop-loss test should not buy")

    class FakeVol:
        current_rsi = Decimal("50")
        current_atr = Decimal("0")
        def update(self):
            return None

    class DummyLog:
        def append(self, trade):
            self.trade = trade

    class DummyStore:
        def save(self, payload):
            self.payload = payload

    market = FakeMarket()
    state = StateMachine()
    state.active_cost_usdt = Decimal("1000")
    state.active_btc = Decimal("0.01")
    state.register_operation("COMPRA_NIVEL_1")
    assert state.is_cooling_down()

    price_engine = PriceEngine(market)
    price_engine.current_price = market.price
    price_engine.peak_price = market.price
    price_engine.last_updated = time.time()

    engine = DecisionEngine(
        market_client=market,
        price_engine=price_engine,
        state_machine=state,
        base_calculator=BaseCalculator(),
        volatility_engine=FakeVol(),
        order_manager=OrderManager(market),
        validator=Validator(market),
        fee_calculator=FeeCalculator(),
        exposure_limiter=ExposureLimiter(),
        bull_protection=BullProtection(),
        trade_log=DummyLog(),
        state_store=DummyStore(),
    )

    engine.on_price_tick(price_engine)
    assert market.sold > Decimal("0")
    assert state.active_btc == Decimal("0.0")
