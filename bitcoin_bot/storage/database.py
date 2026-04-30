import sqlite3
import json
import logging
import time
from pathlib import Path
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)

class DBManager:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id TEXT,
                        client_order_id TEXT,
                        status TEXT,
                        timestamp REAL,
                        datetime TEXT,
                        mode TEXT,
                        side TEXT,
                        symbol TEXT,
                        price TEXT,
                        quantity TEXT,
                        quote_amount TEXT,
                        fee_paid TEXT,
                        fee_qty TEXT,
                        fee_asset TEXT,
                        fee_in_usdt TEXT,
                        reason TEXT
                    )
                ''')
                existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(trades)").fetchall()}
                migrations = {
                    "order_id": "TEXT",
                    "client_order_id": "TEXT",
                    "status": "TEXT",
                    "fee_qty": "TEXT",
                    "fee_asset": "TEXT",
                    "fee_in_usdt": "TEXT",
                }
                for col, col_type in migrations.items():
                    if col not in existing_cols:
                        cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS bot_state (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        updated_at REAL
                    )
                ''')
                conn.commit()
                logger.info(f"Base de datos inicializada en {self.db_path}")
        except Exception as e:
            logger.error(f"Error inicializando base de datos: {e}")

    def insert_trade(self, trade: dict):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                ts = float(trade.get('timestamp', time.time()))
                dt = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                
                price = str(Decimal(str(trade.get('price', 0))))
                qty = str(Decimal(str(trade.get('quantity', 0))))
                quote = str(Decimal(str(trade.get('quote_amount', 0))))
                fee = str(Decimal(str(trade.get('fee_paid', trade.get('fee_in_usdt', 0)))))
                fee_qty = str(Decimal(str(trade.get('fee_qty', trade.get('fee_paid', 0)))))
                fee_in_usdt = str(Decimal(str(trade.get('fee_in_usdt', fee))))
                
                cursor.execute('''
                    INSERT INTO trades (
                        order_id, client_order_id, status, timestamp, datetime, mode, side, symbol,
                        price, quantity, quote_amount, fee_paid, fee_qty, fee_asset, fee_in_usdt, reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    trade.get('order_id', ''), trade.get('client_order_id', ''), trade.get('status', ''),
                    ts, dt, trade.get('mode', 'live'), trade.get('side', ''), trade.get('symbol', ''),
                    price, qty, quote, fee, fee_qty, trade.get('fee_asset', ''), fee_in_usdt, trade.get('reason', '')
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Error insertando trade en BD: {e}")

    def get_all_trades(self):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM trades ORDER BY timestamp DESC')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error consultando trades: {e}")
            return []

    def set_state(self, key: str, value_dict: dict):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO bot_state (key, value, updated_at) 
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                ''', (key, json.dumps(value_dict), time.time()))
                conn.commit()
        except Exception as e:
            logger.error(f"Error guardando estado {key} en BD: {e}")

    def get_state(self, key: str) -> dict:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT value FROM bot_state WHERE key = ?', (key,))
                row = cursor.fetchone()
                if row:
                    return json.loads(row['value'])
        except Exception as e:
            logger.error(f"Error cargando estado {key} de BD: {e}")
        return {}
