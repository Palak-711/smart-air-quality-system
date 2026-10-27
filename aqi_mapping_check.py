
import sqlite3
from pathlib import Path

db_path = (
    Path.home()
    / "OneDrive"
    / "Documents"
    / "aqi_project.db"
)

conn = sqlite3.connect(
    "file:" + db_path.as_posix() + "?mode=ro",
    uri=True,
)

tables = [
    "delhi_aqi_2022_2023_cleaned",
    "faridabad_aqi_2022_2023_cleaned",
    "gurugram_aqi_2022_2023_cleaned",
]

for table in tables:
    print(f"\n--- {table} ---")

    query = f"""
        SELECT
            aqi_category,
            COUNT(*) AS rows_count,
            MIN(aqi) AS min_aqi,
            MAX(aqi) AS max_aqi
        FROM "{table}"
        WHERE aqi_category IS NOT NULL
        GROUP BY aqi_category
        ORDER BY min_aqi
    """

    for row in conn.execute(query):
        print(row)

conn.close()
