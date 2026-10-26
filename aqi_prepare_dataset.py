import sqlite3
from pathlib import Path

import pandas as pd


# --------------------------------------------------
# 1. FILE PATHS
# --------------------------------------------------

documents = Path.home() / "OneDrive" / "Documents"

input_db = documents / "aqi_project_features.db"
output_csv = documents / "aqi_next_hour_dataset.csv"


# --------------------------------------------------
# 2. CITY TABLES
# --------------------------------------------------

city_tables = {
    "Delhi": "delhi_hourly_features",
    "Faridabad": "faridabad_hourly_features",
    "Gurugram": "gurugram_hourly_features",
}


# --------------------------------------------------
# 3. MODELLING FEATURES
# --------------------------------------------------

pollutants = [
    "co",
    "no2",
    "o3",
    "pm10",
    "pm25",
    "so2",
]

feature_columns = ["aqi"] + pollutants

# Add lag features.
for column in feature_columns.copy():
    for lag in [1, 3, 24]:
        feature_columns.append(f"{column}_lag_{lag}")

# Add rolling-average features.
for column in feature_columns.copy():
    if "_lag_" in column:
        continue

    for window in [3, 24]:
        feature_columns.append(
            f"{column}_rolling_mean_{window}h"
        )

# Remove any accidental duplicate column names.
feature_columns = list(dict.fromkeys(feature_columns))


# --------------------------------------------------
# 4. CHECK INPUT DATABASE
# --------------------------------------------------

if not input_db.exists():
    raise FileNotFoundError(
        f"Database not found: {input_db}"
    )

database_uri = input_db.resolve().as_uri() + "?mode=ro"

conn = sqlite3.connect(database_uri, uri=True)

city_datasets = []

try:
    for city, table in city_tables.items():

        print("\n" + "=" * 55)
        print(f"Preparing {city}")
        print("=" * 55)

        df = pd.read_sql_query(
            f'SELECT * FROM "{table}"',
            conn,
        )

        if df.empty:
            raise ValueError(f"{table} contains no records.")

        required_columns = [
            "timestamp",
            "aqi",
        ] + feature_columns

        missing_columns = [
            column
            for column in required_columns
            if column not in df.columns
        ]

        if missing_columns:
            raise ValueError(
                f"Missing columns in {table}: "
                f"{missing_columns}"
            )

        # Parse timestamps and sort chronologically.
        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            errors="raise",
        )

        df = df.sort_values(
            "timestamp"
        ).reset_index(drop=True)

        # Ensure each timestamp is unique.
        if df["timestamp"].duplicated().any():
            raise ValueError(
                f"Duplicate timestamps in {table}."
            )

        # Ensure the timeline is hourly and continuous.
        differences = df["timestamp"].diff().dropna()

        if not differences.eq(
            pd.Timedelta(hours=1)
        ).all():
            raise ValueError(
                f"{table} does not have a continuous "
                "hourly timeline."
            )

        # Convert model features to numeric values.
        for column in feature_columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="raise",
            )

        # --------------------------------------------------
        # 5. CREATE NEXT-HOUR TARGET
        # --------------------------------------------------

        df["target_aqi_next_hour"] = df["aqi"].shift(-1)

        # Record the timestamp the target belongs to.
        df["target_timestamp"] = df["timestamp"].shift(-1)

        # Add city identifier.
        df["city"] = city

        # Add calendar-based features for prediction time.
        df["hour"] = df["timestamp"].dt.hour
        df["day_of_week"] = df["timestamp"].dt.dayofweek
        df["month"] = df["timestamp"].dt.month

        # Select columns for the modelling dataset.
        output_columns = [
            "city",
            "timestamp",
            "target_timestamp",
            "hour",
            "day_of_week",
            "month",
        ] + feature_columns + [
            "target_aqi_next_hour"
        ]

        model_df = df[output_columns].copy()

        # Remove rows with missing inputs or target.
        before = len(model_df)

        model_df = model_df.dropna(
            subset=feature_columns + [
                "target_aqi_next_hour"
            ]
        ).reset_index(drop=True)

        removed = before - len(model_df)

        print("Original rows:", before)
        print("Rows removed due to missing inputs/target:", removed)
        print("Rows ready for modelling:", len(model_df))

        if model_df.empty:
            raise ValueError(
                f"No usable modelling rows for {city}."
            )

        # Confirm the target is one hour after input timestamp.
        target_difference = (
            pd.to_datetime(model_df["target_timestamp"])
            - pd.to_datetime(model_df["timestamp"])
        )

        if not target_difference.eq(
            pd.Timedelta(hours=1)
        ).all():
            raise ValueError(
                f"Target alignment failed for {city}."
            )

        city_datasets.append(model_df)

        print("Target alignment: OK")

finally:
    conn.close()


# --------------------------------------------------
# 6. COMBINE ALL THREE CITIES
# --------------------------------------------------

combined = pd.concat(
    city_datasets,
    ignore_index=True,
)

combined = combined.sort_values(
    ["city", "timestamp"]
).reset_index(drop=True)


# --------------------------------------------------
# 7. SAVE DATASET
# --------------------------------------------------

combined.to_csv(
    output_csv,
    index=False,
)

print("\n" + "=" * 55)
print("DATASET PREPARATION COMPLETED")
print("=" * 55)

print("Total modelling rows:", len(combined))
print("Total columns:", len(combined.columns))
print("Cities:", combined["city"].unique().tolist())
print("Output CSV:", output_csv)

print("\nRows per city:")
print(combined.groupby("city").size())

print("\nSample records:")
print(
    combined[
        [
            "city",
            "timestamp",
            "target_timestamp",
            "aqi",
            "aqi_lag_1",
            "aqi_rolling_mean_24h",
            "target_aqi_next_hour",
        ]
    ].head(5).to_string(index=False)
)

print("\nMissing values in required modelling columns:")

print(
    combined[
        feature_columns + ["target_aqi_next_hour"]
    ].isna().sum().sum()
)

print("\nSUCCESS: Your modelling dataset is ready!")