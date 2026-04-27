import sqlite3
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class DBManager:
    """
    Gestiona la conexión y las operaciones con la base de datos SQLite.
    Se utiliza para persistir las transacciones (trades) y el estado interno del bot (state_machine, base_calculator).
    """
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        # Usamos check_same_thread=False porque la DB puede ser leída desde el thread de Telegram y escrita desde el thread del Trading
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Tabla de trades
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL,
                        datetime TEXT,
                        mode TEXT,
                        side TEXT,
                        symbol TEXT,
                        price REAL,
                        quantity REAL,
                        quote_amount REAL,
                        fee_paid REAL,
                        reason TEXT
                    )
                ''')
                
                # Tabla de estado genérico (clave-valor JSON)
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
                import time
                from datetime import datetime
                ts = trade.get('timestamp', time.time())
                dt = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                
                cursor.execute('''
                    INSERT INTO trades (timestamp, datetime, mode, side, symbol, price, quantity, quote_amount, fee_paid, reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    ts,
                    dt,
                    trade.get('mode', 'live'),
                    trade.get('side', ''),
                    trade.get('symbol', ''),
                    float(trade.get('price', 0)),
                    float(trade.get('quantity', 0)),
                    float(trade.get('quote_amount', 0)),
                    float(trade.get('fee_paid', 0)),
                    trade.get('reason', '')
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
            import time
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
