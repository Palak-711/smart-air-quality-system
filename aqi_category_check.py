
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

for table in tables:
    print(f"\n--- {table} ---")

    query = f"""
        SELECT
            aqi_category,
            MIN(aqi),
            MAX(aqi),
            COUNT(*)
        FROM "{table}"
        WHERE aqi_category IS NOT NULL
        GROUP BY aqi_category
        ORDER BY MIN(aqi)
    """

    for row in conn.execute(query):
        print(row)

conn.close()
