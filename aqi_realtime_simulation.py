import sqlite3
import random
import time
from datetime import datetime
from pathlib import Path
import sys

# Anchor paths to the repository root directory
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import official CPCB calculation and categorization functions
try:
    from api.engine import pm25_to_aqi, aqi_category
except ImportError:
    # Fallback to local common module if api.engine is not in pythonpath
    from aqi_common import pm25_to_aqi, aqi_category

# Base database path anchored relative to repo root
DB_PATH = REPO_ROOT / "data" / "aqi_project.db"

CITIES = ["Delhi", "Faridabad", "Gurugram"]

def generate_simulated_reading(city: str) -> dict:
    """Generate sensor readings and calculate CPCB-compliant AQI values."""
    pm25 = round(random.uniform(15, 150), 2)
    
    # Calculate real AQI and standard CPCB category from PM2.5
    aqi_val = int(pm25_to_aqi(pm25))
    category = aqi_category(aqi_val)

    return {
        "city": city,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "co": round(random.uniform(0.5, 2.0), 2),
        "no2": round(random.uniform(10, 50), 2),
        "o3": round(random.uniform(10, 80), 2),
        "pm10": round(random.uniform(30, 200), 2),
        "pm25": pm25,
        "so2": round(random.uniform(2, 20), 2),
        "aqi": aqi_val,
        "category": category
    }

def init_db(conn: sqlite3.Connection):
    """Ensure table exists before inserting data."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS realtime_aqi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT,
            timestamp TEXT,
            co REAL,
            no2 REAL,
            o3 REAL,
            pm10 REAL,
            pm25 REAL,
            so2 REAL,
            aqi INTEGER,
            category TEXT
        )
    """)
    conn.commit()

def save_reading(conn: sqlite3.Connection, reading: dict):
    """Persist simulated reading to SQLite database."""
    conn.execute("""
        INSERT INTO realtime_aqi
        (city, timestamp, co, no2, o3, pm10, pm25, so2, aqi, category)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        reading["city"],
        reading["timestamp"],
        reading["co"],
        reading["no2"],
        reading["o3"],
        reading["pm10"],
        reading["pm25"],
        reading["so2"],
        reading["aqi"],
        reading["category"]
    ))
    conn.commit()

def main():
    print("Simulated Real-Time AQI Pipeline")
    print(f"Database target: {DB_PATH}")
    print("Press Ctrl+C to stop.\n")

    # Ensure target data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sqlite3.connect(DB_PATH) as conn:
            init_db(conn)
            while True:
                for city in CITIES:
                    reading = generate_simulated_reading(city)
                    save_reading(conn, reading)

                    print(
                        f'{reading["timestamp"]} | '
                        f'{city:10} | AQI: {reading["aqi"]:3d} ({reading["category"]}) | '
                        f'PM2.5: {reading["pm25"]:5.1f}'
                    )

                print("-" * 65)
                time.sleep(10)

    except KeyboardInterrupt:
        print("\nSimulation stopped by user.")

    except sqlite3.Error as error:
        print(f"Database error: {error}")

if __name__ == "__main__":
    main()
