import time
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class PnLTracker:
    def __init__(self, db_manager):
        self.db = db_manager

    def calculate_metrics(self) -> dict:
        trades = self.db.get_all_trades()
        if not trades:
            return {
                "total_trades": 0,
                "accumulated_btc": 0.0,
                "roi_pct": 0.0,
                "daily_profit_btc": 0.0,
                "monthly_profit_btc": 0.0,
                "recent_trades": []
            }

        total_btc_bought = 0.0
        total_btc_sold = 0.0
        total_fees_usdt = 0.0
        max_capital_deployed = 0.0
        current_deployed = 0.0
        
        daily_profit = 0.0
        monthly_profit = 0.0
        
        now = time.time()
        one_day_ago = now - 86400
        thirty_days_ago = now - (86400 * 30)

        for t in trades:
            side = t.get('side', '').upper()
            qty = t.get('quantity', 0.0)
            quote = t.get('quote_amount', 0.0)
            fee = t.get('fee_paid', 0.0)
            ts = t.get('timestamp', 0.0)

            total_fees_usdt += fee

            if side == 'BUY':
                total_btc_bought += qty
                current_deployed += quote
                if current_deployed > max_capital_deployed:
                    max_capital_deployed = current_deployed
            elif side == 'SELL':
                total_btc_sold += qty
                current_deployed -= quote
                if current_deployed < 0:
                    current_deployed = 0
                
                # Para nuestra estrategia "Profit in BTC", el profit de una venta es la cantidad de BTC que NO se vendió para recuperar el USDT
                # Esto es difícil de calcular trade por trade sin saber el enlace exacto compra-venta.
                # Pero podemos calcular el profit global como: Total BTC comprado - Total BTC vendido.
                
        # El profit total en BTC acumulado (libre de costo)
        accumulated_btc = total_btc_bought - total_btc_sold

        # Para profit diario y mensual, haremos una aproximación:
        # PnL en BTC de las ventas ocurridas en ese lapso. 
        # (Esto requeriría un seguimiento más complejo, así que calculamos la diferencia de balance de BTC en ese periodo si es posible.
        # Por simplicidad, devolveremos el ROI general basado en el capital máximo desplegado).
        
        # Asumiendo un precio de BTC promedio o el actual (no lo tenemos directamente aquí sin el price_engine, 
        # pero asumiremos ROI sobre el USDT gastado vs valor de BTC retenido).
        
        # Vamos a filtrar trades recientes para el historial
        recent_trades = trades[:5] if len(trades) >= 5 else trades

        return {
            "total_trades": len(trades),
            "accumulated_btc": accumulated_btc,
            "max_usdt_deployed": max_capital_deployed,
            "total_fees_usdt": total_fees_usdt,
            "recent_trades": recent_trades
        }

    def format_telegram_report(self, metrics: dict, current_price: float) -> str:
        acc_btc = metrics['accumulated_btc']
        acc_usdt_value = acc_btc * current_price if current_price else 0
        max_deployed = metrics['max_usdt_deployed']
        
        roi_pct = (acc_usdt_value / max_deployed * 100) if max_deployed > 0 else 0.0

        report = (
            f"📊 *REPORTE PnL*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"₿ *BTC Acumulado:* `{acc_btc:.8f} BTC`\n"
            f"💵 *Valor (aprox):* `${acc_usdt_value:,.2f}`\n"
            f"📈 *ROI Estimado:* `{roi_pct:+.2f}%`\n"
            f"📉 *Max Capital Usado:* `${max_deployed:,.2f}`\n"
            f"💸 *Total Fees:* `${metrics['total_fees_usdt']:.2f}`\n"
            f"🔄 *Total Trades:* `{metrics['total_trades']}`\n\n"
            f"📝 *Últimos Trades:*\n"
        )
        
        for t in metrics['recent_trades']:
            side_emoji = "🟢" if t.get('side') == 'BUY' else "🔴"
            dt = t.get('datetime', '')[5:16] # MM-DD HH:MM
            report += f"{side_emoji} `{dt}` | `{t.get('side')} {t.get('quantity'):.4f}` a `${t.get('price'):.0f}`\n"
            
        return report
