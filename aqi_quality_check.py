
import sqlite3
from pathlib import Path

db_path = (
    Path.home()
    / "OneDrive"
    / "Documents"
    / "aqi_project_interpolated.db"
)

conn = sqlite3.connect(
    "file:" + db_path.as_posix() + "?mode=ro",
    uri=True
)

cities = [
    "delhi_hourly_interpolated",
    "faridabad_hourly_interpolated",
    "gurugram_hourly_interpolated",
]

columns = ["co", "no2", "o3", "pm10", "pm25", "so2", "aqi"]

for table in cities:
    print("\n---", table, "---")

    duplicates = conn.execute(
        f'SELECT COUNT(*) - COUNT(DISTINCT timestamp) FROM "{table}"'
    ).fetchone()[0]

    print("Duplicate timestamps:", duplicates)

    for column in columns:
        missing = conn.execute(
            f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NULL'
        ).fetchone()[0]

        print(f"{column} missing values: {missing}")

conn.close()
