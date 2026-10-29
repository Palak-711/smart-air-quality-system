import sqlite3
from pathlib import Path

import pandas as pd


# --------------------------------------------------
# 1. DATABASE PATHS
# --------------------------------------------------

documents = Path.home() / "OneDrive" / "Documents"

input_db = documents / "aqi_project_interpolated.db"
output_db = documents / "aqi_project_features.db"


# --------------------------------------------------
# 2. CITY TABLES
# --------------------------------------------------

city_tables = {
    "delhi_hourly_interpolated": "delhi_hourly_features",
    "faridabad_hourly_interpolated": "faridabad_hourly_features",
    "gurugram_hourly_interpolated": "gurugram_hourly_features",
}


# --------------------------------------------------
# 3. FORECASTING FEATURES
# --------------------------------------------------

variables = [
    "aqi",
    "co",
    "no2",
    "o3",
    "pm10",
    "pm25",
    "so2",
]

lag_hours = [1, 3, 24]
rolling_hours = [3, 24]


# --------------------------------------------------
# 4. FIND THE TIMESTAMP COLUMN
# --------------------------------------------------

possible_timestamp_names = [
    "timestamp",
    "datetime",
    "date_time",
    "date",
    "time",
]


def find_timestamp_column(columns):
    column_lookup = {
        str(column).lower(): column
        for column in columns
    }

    for name in possible_timestamp_names:
        if name in column_lookup:
            return column_lookup[name]

    raise ValueError(
        "Could not find a timestamp column. "
        f"Available columns: {list(columns)}"
    )


# --------------------------------------------------
# 5. CHECK INPUT DATABASE
# --------------------------------------------------

if not input_db.exists():
    raise FileNotFoundError(
        f"Input database not found:\n{input_db}\n"
        "Check that the file exists in your Documents folder."
    )

print("=" * 60)
print("AQI FEATURE ENGINEERING")
print("=" * 60)

print(f"\nInput database:  {input_db}")
print(f"Output database: {output_db}")


# Open the original interpolated database as read-only.
source_uri = input_db.resolve().as_uri() + "?mode=ro"

source_conn = sqlite3.connect(
    source_uri,
    uri=True,
)

# This is a separate database for the new feature tables.
output_conn = sqlite3.connect(output_db)


try:
    # --------------------------------------------------
    # 6. PROCESS EACH CITY
    # --------------------------------------------------

    for source_table, output_table in city_tables.items():

        print("\n" + "-" * 60)
        print(f"Processing: {source_table}")
        print("-" * 60)

        # Read source table.
        df = pd.read_sql_query(
            f'SELECT * FROM "{source_table}"',
            source_conn,
        )

        original_rows = len(df)

        if original_rows == 0:
            raise ValueError(
                f"The source table {source_table} is empty."
            )

        # Find and parse the timestamp column.
        timestamp_col = find_timestamp_column(df.columns)

        df[timestamp_col] = pd.to_datetime(
            df[timestamp_col],
            errors="raise",
        )

        # Sort chronologically before creating features.
        df = df.sort_values(
            timestamp_col
        ).reset_index(drop=True)

        # Ensure timestamps are unique.
        if df[timestamp_col].duplicated().any():
            raise ValueError(
                f"Duplicate timestamps found in {source_table}."
            )

        # Verify that the data is hourly and continuous.
        time_difference = df[timestamp_col].diff().dropna()

        if not time_difference.eq(pd.Timedelta(hours=1)).all():
            raise ValueError(
                f"{source_table} does not have a continuous "
                "hourly timeline. Check timestamps before "
                "creating time-based features."
            )

        # Check which pollutant/AQI columns exist.
        available_variables = [
            column
            for column in variables
            if column in df.columns
        ]

        if "aqi" not in available_variables:
            raise ValueError(
                f"No 'aqi' column found in {source_table}."
            )

        # Convert available variables to numeric values.
        for column in available_variables:
            df[column] = pd.to_numeric(
                df[column],
                errors="raise",
            )

        # --------------------------------------------------
        # 7. CREATE LAG FEATURES
        # --------------------------------------------------

        for column in available_variables:

            for lag in lag_hours:

                feature_name = f"{column}_lag_{lag}"

                df[feature_name] = df[column].shift(lag)

        # --------------------------------------------------
        # 8. CREATE ROLLING AVERAGES
        # --------------------------------------------------

        for column in available_variables:

            # Shift by one hour first so the current reading
            # is not included in its own rolling average.
            previous_values = df[column].shift(1)

            for window in rolling_hours:

                feature_name = (
                    f"{column}_rolling_mean_{window}h"
                )

                df[feature_name] = (
                    previous_values
                    .rolling(
                        window=window,
                        min_periods=window,
                    )
                    .mean()
                )

        # --------------------------------------------------
        # 9. SAVE TO THE SEPARATE OUTPUT DATABASE
        # --------------------------------------------------

        df.to_sql(
            output_table,
            output_conn,
            if_exists="replace",
            index=False,
        )

        output_conn.commit()

        # --------------------------------------------------
        # 10. VERIFY THE RESULTS
        # --------------------------------------------------

        saved_rows = output_conn.execute(
            f'SELECT COUNT(*) FROM "{output_table}"'
        ).fetchone()[0]

        print(f"Timestamp column: {timestamp_col}")
        print(f"Rows in source:   {original_rows}")
        print(f"Rows saved:       {saved_rows}")
        print(f"Variables used:   {available_variables}")

        print("\nCreated features:")

        feature_columns = [
            column
            for column in df.columns
            if "_lag_" in column
            or "_rolling_mean_" in column
        ]

        for column in feature_columns:
            print(f"  - {column}")

        print("\nMissing values in selected AQI features:")

        aqi_feature_columns = [
            "aqi_lag_1",
            "aqi_lag_3",
            "aqi_lag_24",
            "aqi_rolling_mean_3h",
            "aqi_rolling_mean_24h",
        ]

        for column in aqi_feature_columns:
            missing = int(df[column].isna().sum())
            print(f"  {column}: {missing}")

        if saved_rows != original_rows:
            raise ValueError(
                f"Row count changed for {output_table}."
            )

        print(f"\nSUCCESS: {output_table} created.")

finally:
    source_conn.close()
    output_conn.close()


print("\n" + "=" * 60)
print("FEATURE ENGINEERING COMPLETED SUCCESSFULLY!")
print(f"Output database: {output_db}")
print("=" * 60)