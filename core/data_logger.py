import logging
import sqlite3
import os
from typing import Dict, Any

class DataLogger:
    """
    Records trade outcomes into a SQLite database.
    (Note: README specifies SQLAlchemy, but we implement basic stdlib sqlite3 here 
     for the alpha phase to minimize dependency complexity initially. 
     This can be upgraded to SQLAlchemy later.)
    """

    def __init__(self, db_path: str = "./data/trades.db"):
        self.db_path = db_path
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self._ensure_dir()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_schema()

    def _ensure_dir(self):
        """Create directory if not exists."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _init_schema(self):
        """Create the trades table if it does not exist."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    market_id TEXT,
                    mode TEXT,
                    size_usd REAL,
                    spread REAL,
                    estimated_profit REAL,
                    status TEXT
                )
            """)
            self.conn.commit()
        except sqlite3.Error as e:
            self.logger.error(f"Error initializing database schema: {e}")

    def log_trade(self, trade_data: Dict[str, Any]):
        """
        Insert trade record.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO trades (market_id, mode, size_usd, spread, estimated_profit, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                trade_data.get("market_id"),
                trade_data.get("mode"),
                trade_data.get("size_usd"),
                trade_data.get("spread"),
                trade_data.get("estimated_profit"),
                trade_data.get("status")
            ))
            self.conn.commit()
        except sqlite3.Error as e:
            self.logger.error(f"Failed to log trade to DB: {e}")

    def close(self):
        """Close connection gracefully."""
        if self.conn:
            self.conn.close()
