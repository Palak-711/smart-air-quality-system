import sqlite3
import random
import time
from datetime import datetime

# Existing project database
DB_PATH = r"C:\Users\Radha\OneDrive\Documents\aqi_project.db"

CITIES = ["Delhi", "Faridabad", "Gurugram"]

def generate_simulated_reading(city):
    """Generate example AQI sensor readings for simulation."""

    return {
        "city": city,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "co": round(random.uniform(0.5, 2.0), 2),
        "no2": round(random.uniform(10, 50), 2),
        "o3": round(random.uniform(10, 80), 2),
        "pm10": round(random.uniform(30, 200), 2),
        "pm25": round(random.uniform(15, 150), 2),
        "so2": round(random.uniform(2, 20), 2),
        "aqi": random.randint(50, 300)
    }

def save_reading(conn, reading):
    conn.execute("""
        INSERT INTO realtime_aqi
        (city, timestamp, co, no2, o3, pm10, pm25, so2, aqi)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        reading["city"],
        reading["timestamp"],
        reading["co"],
        reading["no2"],
        reading["o3"],
        reading["pm10"],
        reading["pm25"],
        reading["so2"],
        reading["aqi"]
    ))

    conn.commit()

def main():
    print("Simulated Real-Time AQI Pipeline")
    print("Press Ctrl+C to stop.\n")

    try:
        with sqlite3.connect(DB_PATH) as conn:
            while True:
                for city in CITIES:
                    reading = generate_simulated_reading(city)
                    save_reading(conn, reading)

                    print(
                        f'{reading["timestamp"]} | '
                        f'{city} | AQI: {reading["aqi"]} | '
                        f'PM2.5: {reading["pm25"]}'
                    )

                print("-" * 55)
                time.sleep(10)

    except KeyboardInterrupt:
        print("\nSimulation stopped.")

    except sqlite3.Error as error:
        print(f"Database error: {error}")

if __name__ == "__main__":
    main()