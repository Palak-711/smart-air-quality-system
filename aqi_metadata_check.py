
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
    uri=True,
)

tables = [
    "delhi_hourly_interpolated",
    "faridabad_hourly_interpolated",
    "gurugram_hourly_interpolated",
]

columns = [
    "aqi_category",
    "location_name",
    "location_lat",
    "location_lon",
]

for table in tables:
    print(f"\n--- {table} ---")

    for column in columns:
        query = (
            f'SELECT COUNT(*) FROM "{table}" '
            f'WHERE "{column}" IS NULL'
        )
        missing = conn.execute(query).fetchone()[0]
        print(f"{column} missing: {missing}")

    query = (
        f'SELECT aqi_category, COUNT(*) '
        f'FROM "{table}" '
        f'GROUP BY aqi_category '
        f'ORDER BY aqi_category'
    )
    categories = conn.execute(query).fetchall()
    print("Categories:", categories)

conn.close()
