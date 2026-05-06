import os
import json
import logging
from decimal import Decimal
from bitcoin_bot.storage.state_store import FileStateStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def inject_btc():
    logger.info("Iniciando inyeccion de 50% BTC...")
    
    # Path of state.json in production
    state_file = "/opt/bitcoin-bot/data/state.json"
    
    if not os.path.exists(state_file):
        logger.error(f"No se encontro {state_file}. El bot debe ejecutarse al menos una vez antes de inyectar.")
        return

    # Load store
    store = FileStateStore(data_dir="/opt/bitcoin-bot/data")
    data = store.load()
    
    if not data or "state_machine" not in data:
        logger.error("State invalido o vacio.")
        return

    sm_data = data["state_machine"]
    
    # El baseline_btc representa el balance real que habia antes.
    # En el screenshot, tenias ~0.00328921 BTC.
    # Leer el baseline actual o usar un hardcode si falla.
    baseline = Decimal(sm_data.get("baseline_btc") or "0.0")
    if baseline <= 0:
        logger.warning("baseline_btc es 0 o null. Asegurate de reanudar el bot al menos una vez para que cuadre el baseline antes de inyectar.")
        # Podemos intentar pedirle al usuario que meta el balance manual si es 0, pero vamos a asumir que ya le dio Resume.
        
    logger.info(f"Balance base detectado: {baseline} BTC")
    
    # Queremos inyectar el 50% del balance base
    if baseline <= 0:
        baseline = Decimal("0.00328921") # Hardcode fallback based on screenshot
        logger.info(f"Usando fallback balance: {baseline}")
        
    injection_amount = baseline / Decimal("2.0")
    logger.info(f"Monto a inyectar (50%): {injection_amount:.8f} BTC")
    
    # Obtener el precio actual de mercado. Si no está en el state, usamos fallback.
    last_price = Decimal(data.get("last_price", "80000.0"))
    if last_price <= 0: last_price = Decimal("80000.0")
    
    # Calcular costo de la inyección para que sepa cuándo vender a ganancia
    cost_usdt = injection_amount * last_price
    
    # Actualizar estado
    sm_data["active_btc"] = str(injection_amount)
    sm_data["active_cost_usdt"] = str(cost_usdt)
    sm_data["state"] = "EN_SUBIDA"
    
    # Ajustamos baseline. Si el baseline incluye el BTC que vamos a hacer "activo",
    # expected_delta será active_btc + accumulated_btc.
    # actual_delta será real_balance - baseline.
    # real_balance es ~baseline. actual_delta será 0.
    # expected_delta será injection_amount (que NO es 0).
    # Para que cuadre la reconciliacion: 
    # actual_delta = expected_delta
    # real_balance - nuevo_baseline = injection_amount
    # nuevo_baseline = real_balance - injection_amount
    nuevo_baseline = baseline - injection_amount
    sm_data["baseline_btc"] = str(nuevo_baseline)
    
    data["state_machine"] = sm_data
    store.save(data)
    
    logger.info("=======================================")
    logger.info(f"✅ INYECCION EXITOSA")
    logger.info(f"   BTC Inyectado:  {injection_amount:.8f} BTC")
    logger.info(f"   Precio Costo:   ${last_price:,.2f}")
    logger.info(f"   Costo Activo:   ${cost_usdt:,.2f} USDT")
    logger.info(f"   Nuevo Baseline: {nuevo_baseline:.8f} BTC")
    logger.info("=======================================")
    logger.info("Ahora reinicia el bot: sudo systemctl restart bitcoin-bot")

if __name__ == "__main__":
    inject_btc()
