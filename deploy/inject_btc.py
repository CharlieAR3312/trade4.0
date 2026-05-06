import os
import logging
from decimal import Decimal
from bitcoin_bot.storage.database import DBManager
from bitcoin_bot.storage.state_store import StateStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def inject_btc():
    logger.info("Iniciando inyeccion de 50% BTC...")
    
    db_path = "/opt/bitcoin-bot/data/bot.db"
    if not os.path.exists(db_path):
        logger.error(f"No se encontro {db_path}. El bot debe ejecutarse al menos una vez antes de inyectar.")
        return

    db_manager = DBManager(db_path)
    store = StateStore(db_manager)
    
    data = store.load()
    
    if not data or "state_machine" not in data:
        logger.error("State invalido o vacio.")
        return

    sm_data = data["state_machine"]
    
    baseline = Decimal(sm_data.get("baseline_btc") or "0.0")
    if baseline <= 0:
        logger.warning("baseline_btc es 0 o null. Asegurate de reanudar el bot al menos una vez para que cuadre el baseline.")
        
    logger.info(f"Balance base detectado: {baseline} BTC")
    
    if baseline <= 0:
        baseline = Decimal("0.00328921")
        logger.info(f"Usando fallback balance: {baseline}")
        
    injection_amount = baseline / Decimal("2.0")
    logger.info(f"Monto a inyectar (50%): {injection_amount:.8f} BTC")
    
    last_price = Decimal(data.get("last_price", "80000.0"))
    if last_price <= 0: last_price = Decimal("80000.0")
    
    cost_usdt = injection_amount * last_price
    
    sm_data["active_btc"] = str(injection_amount)
    sm_data["active_cost_usdt"] = str(cost_usdt)
    sm_data["state"] = "EN_SUBIDA"
    
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
