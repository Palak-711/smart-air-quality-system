
import os
import sys
import joblib
import numpy as np
import pandas as pd


# --------------------------------------------------
# 1. FILE PATHS
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATASET_PATH = os.path.join(
    BASE_DIR, "aqi_next_hour_dataset.csv"
)

MODEL_PATH = os.path.join(
    BASE_DIR, "aqi_forecasting_model.joblib"
)


# --------------------------------------------------
# 2. MAIN FUNCTION
# --------------------------------------------------

def main():

    print("=" * 50)
    print("       AQI NEXT-HOUR PREDICTION")
    print("=" * 50)

    # Check required files
    if not os.path.exists(MODEL_PATH):
        print("ERROR: Trained model not found.")
        print("Expected:", MODEL_PATH)
        sys.exit(1)

    if not os.path.exists(DATASET_PATH):
        print("ERROR: Dataset not found.")
        print("Expected:", DATASET_PATH)
        sys.exit(1)

    # --------------------------------------------------
    # 3. LOAD TRAINED MODEL
    # --------------------------------------------------

    print("\nLoading trained model...")

    bundle = joblib.load(MODEL_PATH)

    model = bundle["model"]
    feature_columns = bundle["feature_columns"]
    feature_medians = bundle["feature_medians"]

    print("Model loaded successfully!")

    # --------------------------------------------------
    # 4. LOAD DATASET
    # --------------------------------------------------

    print("\nLoading AQI dataset...")

    df = pd.read_csv(DATASET_PATH)

    required = ["city", "timestamp", "target_aqi_next_hour"]

    missing = [col for col in required if col not in df.columns]

    if missing:
        print("ERROR: Missing required columns:", missing)
        sys.exit(1)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"], errors="coerce"
    )

    df = df.dropna(
        subset=["city", "timestamp"]
    ).copy()

    df["city"] = df["city"].astype(str)

    df = df.sort_values(
        ["city", "timestamp"]
    ).reset_index(drop=True)

    # --------------------------------------------------
    # 5. SELECT LATEST AVAILABLE ROW PER CITY
    # --------------------------------------------------

    latest_rows = (
        df.groupby("city", sort=True)
        .tail(1)
        .copy()
        .reset_index(drop=True)
    )

    if latest_rows.empty:
        print("ERROR: No usable AQI records found.")
        sys.exit(1)

    print("\nLatest records selected:")
    print(
        latest_rows[["city", "timestamp"]].to_string(index=False)
    )

    # --------------------------------------------------
    # 6. PREPARE INPUT FEATURES
    # --------------------------------------------------

    excluded_columns = {
        "target_aqi_next_hour",
        "timestamp",
        "target_timestamp"
    }

    available_features = [
        col for col in df.columns
        if col not in excluded_columns
    ]

    missing_features = [
        col for col in available_features
        if col not in latest_rows.columns
    ]

    if missing_features:
        print("ERROR: Missing input features:", missing_features)
        sys.exit(1)

    X = latest_rows[available_features].copy()

    # Encode city in the same way as during training
    X = pd.get_dummies(
        X, columns=["city"], dtype=int
    )

    # Match the exact feature columns used during training
    X = X.reindex(
        columns=feature_columns,
        fill_value=0
    )

    X = X.apply(
        pd.to_numeric, errors="coerce"
    )

    X = X.replace(
        [np.inf, -np.inf], np.nan
    )

    medians = pd.Series(feature_medians)

    X = X.fillna(medians).fillna(0)

    # --------------------------------------------------
    # 7. PREDICT NEXT-HOUR AQI
    # --------------------------------------------------

    print("\nGenerating predictions...")

    predictions = model.predict(X)

    # --------------------------------------------------
    # 8. DISPLAY RESULTS
    # --------------------------------------------------

    results = pd.DataFrame({
        "city": latest_rows["city"].to_numpy(),
        "latest_timestamp": latest_rows["timestamp"].to_numpy(),
        "latest_record_aqi": (
            pd.to_numeric(
                latest_rows["aqi"], errors="coerce"
            ).to_numpy()
            if "aqi" in latest_rows.columns
            else np.full(len(latest_rows), np.nan)
        ),
        "predicted_next_hour_aqi": predictions
    })

    # Dataset timestamps represent the time of the input record.
    # The forecast is for the following hour.
    results["forecast_timestamp"] = (
        pd.to_datetime(results["latest_timestamp"])
        + pd.Timedelta(hours=1)
    )

    results = results[
        [
            "city",
            "latest_timestamp",
            "latest_record_aqi",
            "forecast_timestamp",
            "predicted_next_hour_aqi"
        ]
    ]

    print("\n" + "=" * 70)
    print("             NEXT-HOUR AQI FORECAST")
    print("=" * 70)

    print(results.to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    # --------------------------------------------------
    # 9. SAVE PREDICTIONS
    # --------------------------------------------------

    output_path = os.path.join(
        BASE_DIR, "aqi_next_hour_forecast.csv"
    )

    results.to_csv(output_path, index=False)

    print("\nForecast saved to:")
    print(output_path)

    print("\nPrediction process completed!")


# --------------------------------------------------
# 10. RUN PROGRAM
# --------------------------------------------------

if __name__ == "__main__":
    main()
