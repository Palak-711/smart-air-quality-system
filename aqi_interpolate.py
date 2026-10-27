
import sqlite3
import pandas as pd
from pathlib import Path

# --------------------------------------------------
# 1. Database paths
# --------------------------------------------------

DB_PATH = (
    Path.home()
    / "OneDrive"
    / "Documents"
    / "aqi_project.db"
)

OUTPUT_DB = DB_PATH.with_name(
    "aqi_project_interpolated.db"
)

# --------------------------------------------------
# 2. Source tables and city names
# --------------------------------------------------

TABLES = {
    "delhi_aqi_2022_2023_cleaned": "delhi",
    "faridabad_aqi_2022_2023_cleaned": "faridabad",
    "gurugram_aqi_2022_2023_cleaned": "gurugram",
}

VALUE_COLUMNS = [
    "co",
    "no2",
    "o3",
    "pm10",
    "pm25",
    "so2",
    "aqi",
]

# Complete hourly timeline: 2022–2023
hourly_index = pd.date_range(
    start="2022-01-01 00:00:00",
    end="2023-12-31 23:00:00",
    freq="h",
    name="timestamp",
)

# --------------------------------------------------
# 3. Check database files
# --------------------------------------------------

if not DB_PATH.exists():
    raise FileNotFoundError(
        f"Original database not found: {DB_PATH}"
    )

# Open original database in read-only mode
source_uri = DB_PATH.as_uri() + "?mode=ro"

print("Original database:", DB_PATH)
print("Output database:", OUTPUT_DB)
print()

# --------------------------------------------------
# 4. Process each city
# --------------------------------------------------

with sqlite3.connect(source_uri, uri=True) as source:

    # Write only to the separate output database
    with sqlite3.connect(OUTPUT_DB) as output:

        for source_table, city in TABLES.items():

            print(f"Processing {city.title()}...")

            # Load source data
            df = pd.read_sql_query(
                f'SELECT * FROM "{source_table}"',
                source,
            )

            if df.empty:
                raise ValueError(
                    f"No data found in {source_table}"
                )

            # Convert timestamps
            df["timestamp"] = pd.to_datetime(
                df["timestamp"],
                errors="raise",
            )

            df = df.sort_values("timestamp")

            # Validate original timestamps
            if df["timestamp"].duplicated().any():
                raise ValueError(
                    f"Duplicate timestamps in {source_table}"
                )

            # Record timestamps present in original data
            original_timestamps = pd.DatetimeIndex(
                df["timestamp"]
            )

            # Set timestamp as index and create full timeline
            df = df.set_index("timestamp")
            df = df.reindex(hourly_index)

            # Identify rows by timestamp origin
            df["data_source"] = "interpolated"
            df.loc[
                df.index.isin(original_timestamps),
                "data_source",
            ] = "original"

            # Interpolate numerical pollution values only
            cols = [
                col
                for col in VALUE_COLUMNS
                if col in df.columns
            ]

            df[cols] = df[cols].interpolate(
                method="time",
                limit=3,
                limit_area="inside",
            )

            # Recalculate calendar features
            df["hour"] = df.index.hour
            df["day"] = df.index.day
            df["month"] = df.index.month
            df["year"] = df.index.year
            df["day_of_week"] = df.index.dayofweek
            df["is_weekend"] = (
                df.index.dayofweek >= 5
            ).astype(int)

            # Restore timestamp as a regular column
            df = df.reset_index()

            # Output table for this city
            output_table = (
                f"{city}_hourly_interpolated"
            )

            # Save to the separate output database
            df.to_sql(
                output_table,
                output,
                if_exists="replace",
                index=False,
            )

            # Quality checks
            total_rows = len(df)

            original_rows = int(
                (df["data_source"] == "original").sum()
            )

            interpolated_rows = int(
                (df["data_source"] == "interpolated").sum()
            )

            remaining_missing = int(
                df[cols].isna().sum().sum()
            )

            duplicate_count = int(
                df["timestamp"].duplicated().sum()
            )

            print(f"  Table: {output_table}")
            print(f"  Total rows: {total_rows}")
            print(f"  Original timestamp rows: {original_rows}")
            print(f"  Added timestamp rows: {interpolated_rows}")
            print(f"  Remaining missing pollution values: {remaining_missing}")
            print(f"  Duplicate timestamps: {duplicate_count}")
            print()

print("Finished processing all cities.")
print("Output database:", OUTPUT_DB)
