import time
from datetime import datetime
from decimal import Decimal
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
                "accumulated_btc": Decimal("0.0"),
                "total_fees_usdt": Decimal("0.0"),
                "max_usdt_deployed": Decimal("0.0"),
                "recent_trades": []
            }

        total_btc_bought = Decimal("0.0")
        total_btc_sold = Decimal("0.0")
        total_fees_usdt = Decimal("0.0")
        max_capital_deployed = Decimal("0.0")
        current_deployed = Decimal("0.0")
        
        for t in trades:
            side = str(t.get('side', '')).upper()
            qty = Decimal(str(t.get('quantity', 0.0)))
            quote = Decimal(str(t.get('quote_amount', 0.0)))
            fee = Decimal(str(t.get('fee_in_usdt', t.get('fee_paid', 0.0))))

            total_fees_usdt += fee

            if side == 'BUY':
                total_btc_bought += qty
                current_deployed += quote
                if current_deployed > max_capital_deployed:
                    max_capital_deployed = current_deployed
            elif side == 'SELL':
                total_btc_sold += qty
                current_deployed -= (quote - fee) # Recuperamos el neto
                if current_deployed < 0:
                    current_deployed = Decimal("0.0")
                
        accumulated_btc = total_btc_bought - total_btc_sold
        recent_trades = trades[:5] if len(trades) >= 5 else trades

        return {
            "total_trades": len(trades),
            "accumulated_btc": accumulated_btc,
            "max_usdt_deployed": max_capital_deployed,
            "total_fees_usdt": total_fees_usdt,
            "recent_trades": recent_trades
        }

    def format_telegram_report(self, metrics: dict, current_price: Decimal | float) -> str:
        acc_btc = metrics['accumulated_btc']
        current_price = Decimal(str(current_price))
        acc_usdt_value = acc_btc * current_price if current_price else Decimal("0.0")
        max_deployed = metrics['max_usdt_deployed']
        
        roi_pct = (acc_usdt_value / max_deployed * Decimal("100")) if max_deployed > 0 else Decimal("0.0")

        report = (
            f"📊 *REPORTE PnL*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"₿ *BTC Acumulado:* `{float(acc_btc):.8f} BTC`\n"
            f"💵 *Valor (aprox):* `${float(acc_usdt_value):,.2f}`\n"
            f"📈 *ROI Estimado:* `{float(roi_pct):+.2f}%`\n"
            f"📉 *Max Capital Usado:* `${float(max_deployed):,.2f}`\n"
            f"💸 *Total Fees:* `${float(metrics['total_fees_usdt']):.2f}`\n"
            f"🔄 *Total Trades:* `{metrics['total_trades']}`\n\n"
            f"📝 *Últimos Trades:*\n"
        )
        
        for t in metrics['recent_trades']:
            side_emoji = "🟢" if t.get('side') == 'BUY' else "🔴"
            dt = str(t.get('datetime', ''))[5:16]
            report += f"{side_emoji} `{dt}` | `{t.get('side')} {float(t.get('quantity', 0)):.4f}` a `${float(t.get('price', 0)):.0f}`\n"
            
        return report
