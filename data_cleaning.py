import pandas as pd
import numpy as np
from pathlib import Path

# Project paths
BASE_DIR = Path(__file__).resolve().parent

INPUT_DIR = BASE_DIR / "data" / "cleaned"

OUTPUT_DIR = BASE_DIR / "data" / "cleaned_gap_filled"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Pollutant columns
POLLUTANTS = ["pm25", "pm10", "no2", "so2", "co", "o3"]

# Cities
CITIES = ["delhi", "faridabad", "gurugram"]


def clean_city_data(filepath, city_name):

    print(f"\nProcessing {city_name}...")

    # Read cleaned dataset
    df = pd.read_csv(filepath)

    # Convert timestamp
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], errors="coerce"
    )

    df = df.dropna(subset=["timestamp"])

    # Sort timestamps
    df = df.sort_values("timestamp")

    # Remove duplicate timestamps
    duplicate_count = df["timestamp"].duplicated().sum()

    df = df.drop_duplicates(
        subset=["timestamp"], keep="first"
    )

    df = df.set_index("timestamp")

    # Mark original records
    df["data_source"] = "original"

    # Create complete hourly index
    full_index = pd.date_range(
        start=df.index.min(),
        end=df.index.max(),
        freq="h"
    )

    original_count = len(df)

    # Insert missing timestamps
    df = df.reindex(full_index)

    df.index.name = "timestamp"

    # Identify inserted records
    df["data_source"] = df["data_source"].fillna(
        "inserted"
    )

    inserted_count = (
        df["data_source"] == "inserted"
    ).sum()

    # Convert pollutant columns to numeric
    for col in POLLUTANTS:

        if col in df.columns:

            df[col] = pd.to_numeric(
                df[col], errors="coerce"
            )

            # Treat zero as missing
            df.loc[df[col] == 0, col] = np.nan

    # Flag outliers using IQR
    df["is_outlier"] = False

    for col in POLLUTANTS:

        if col in df.columns:

            q1 = df[col].quantile(0.25)
            q3 = df[col].quantile(0.75)

            iqr = q3 - q1

            upper_limit = q3 + (1.5 * iqr)

            df.loc[
                df[col] > upper_limit,
                "is_outlier"
            ] = True

    # Fill missing pollutant values
    # Maximum 3 consecutive hours
    for col in POLLUTANTS:

        if col in df.columns:

            df[col] = df[col].ffill(limit=3)

    # Restore location information
    for col in [
        "location_name",
        "location_lat",
        "location_lon"
    ]:

        if col in df.columns:

            df[col] = df[col].ffill().bfill()

    # Update time-based features
    df["hour"] = df.index.hour
    df["day"] = df.index.day
    df["month"] = df.index.month
    df["year"] = df.index.year
    df["day_of_week"] = df.index.dayofweek

    df["is_weekend"] = (
        df["day_of_week"] >= 5
    ).astype(int)

    return df, original_count, inserted_count, duplicate_count


# Main execution
if __name__ == "__main__":

    for city in CITIES:

        input_path = (
            INPUT_DIR /
            f"{city}_aqi_2022_2023_cleaned.csv"
        )

        if input_path.exists():

            cleaned_df, original_count, inserted_count, duplicate_count = (
                clean_city_data(input_path, city.title())
            )

            # Save final output separately
            output_path = (
                OUTPUT_DIR / f"{city}_cleaned.csv"
            )

            cleaned_df.reset_index().to_csv(
                output_path, index=False
            )

            print(f"\nSaved: {output_path}")

            print("Original records:", original_count)

            print("Final records:", len(cleaned_df))

            print("Inserted timestamps:", inserted_count)

            print("Duplicates removed:", duplicate_count)

            print("\nRemaining missing pollutant values:")

            print(cleaned_df[POLLUTANTS].isnull().sum())

        else:

            print(f"File not found: {input_path}")

    print("\nData cleaning completed!")