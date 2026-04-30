import pytest
from decimal import Decimal
from bitcoin_bot.core.state_machine import StateMachine, BotState
from bitcoin_bot.core.models import OrderExecution

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
