import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "aqi_live.db"

class Store:
    """SQLite storage engine for telemetry logs, predictions, and actuation events."""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT (datetime('now')),
                    city TEXT,
                    raw_pm25 REAL,
                    calibrated_pm25 REAL,
                    aqi REAL,
                    aqi_category TEXT,
                    window_state TEXT,
                    fan_state TEXT,
                    purifier_state TEXT
                )
            """)
            conn.commit()

    def log_telemetry(self, city: str, raw_pm25: float, calibrated_pm25: float, 
                      aqi: float, aqi_category: str, window_state: str, 
                      fan_state: str, purifier_state: str):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO telemetry_log 
                (city, raw_pm25, calibrated_pm25, aqi, aqi_category, window_state, fan_state, purifier_state)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (city, raw_pm25, calibrated_pm25, aqi, aqi_category, window_state, fan_state, purifier_state))
            conn.commit()

    def get_recent_logs(self, city: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            if city:
                cursor = conn.execute(
                    "SELECT * FROM telemetry_log WHERE LOWER(city) = LOWER(?) ORDER BY id DESC LIMIT ?", 
                    (city, limit)
                )
            else:
                cursor = conn.execute("SELECT * FROM telemetry_log ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]
