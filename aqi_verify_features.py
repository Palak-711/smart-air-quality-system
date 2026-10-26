import sqlite3
from pathlib import Path

db_path = (
    Path.home()
    / "OneDrive"
    / "Documents"
    / "aqi_project_features.db"
)

conn = sqlite3.connect(
    "file:" + db_path.as_posix() + "?mode=ro",
    uri=True,
)

tables = [
    "delhi_hourly_features",
    "faridabad_hourly_features",
    "gurugram_hourly_features",
]

for table in tables:
    print("\n" + "=" * 55)
    print(table)
    print("=" * 55)

    # Check row count
    count = conn.execute(
        f'SELECT COUNT(*) FROM "{table}"'
    ).fetchone()[0]

    print("Total rows:", count)

    # Check first five records
    query = f"""
        SELECT
            timestamp,
            aqi,
            aqi_lag_1,
            aqi_lag_3,
            aqi_lag_24,
            aqi_rolling_mean_3h,
            aqi_rolling_mean_24h
        FROM "{table}"
        ORDER BY timestamp
        LIMIT 5
    """

    print("\nFirst five records:")

    for row in conn.execute(query):
        print(row)

    # Check the final record
    query = f"""
        SELECT
            timestamp,
            aqi,
            aqi_lag_1,
            aqi_rolling_mean_3h,
            aqi_rolling_mean_24h
        FROM "{table}"
        ORDER BY timestamp DESC
        LIMIT 1
    """

    print("\nLast record:")

    for row in conn.execute(query):
        print(row)

conn.close()

print("\nVerification completed.")