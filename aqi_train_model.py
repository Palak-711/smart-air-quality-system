import os
import sys
import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


# File paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATASET_PATH = os.path.join(BASE_DIR, "aqi_next_hour_dataset.csv")
MODEL_PATH = os.path.join(BASE_DIR, "aqi_forecasting_model.joblib")
PREDICTIONS_PATH = os.path.join(BASE_DIR, "aqi_test_predictions.csv")


def main():

    print("Starting AQI Forecasting Model...")

    # Load dataset
    if not os.path.exists(DATASET_PATH):
        print("ERROR: Dataset file not found:", DATASET_PATH)
        sys.exit(1)

    df = pd.read_csv(DATASET_PATH)

    required_columns = [
        "city",
        "timestamp",
        "target_aqi_next_hour"
    ]

    missing_columns = [
        col for col in required_columns
        if col not in df.columns
    ]

    if missing_columns:
        print("ERROR: Missing columns:", missing_columns)
        print("Available columns:", df.columns.tolist())
        sys.exit(1)

    # Clean dataset
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], errors="coerce"
    )

    df["target_aqi_next_hour"] = pd.to_numeric(
        df["target_aqi_next_hour"], errors="coerce"
    )

    df = df.dropna(
        subset=["city", "timestamp", "target_aqi_next_hour"]
    ).copy()

    if df.empty:
        print("ERROR: No valid data available.")
        sys.exit(1)

    df["city"] = df["city"].astype(str)

    df = df.sort_values(
        ["city", "timestamp"]
    ).reset_index(drop=True)

    print("Dataset loaded successfully!")
    print("Total rows:", len(df))
    print("Cities:", df["city"].unique())

    # Split data chronologically for each city
    train_parts = []
    test_parts = []

    for city, city_df in df.groupby("city", sort=True):

        city_df = city_df.sort_values(
            "timestamp"
        ).reset_index(drop=True)

        if len(city_df) < 5:
            print("Skipping city with insufficient data:", city)
            continue

        split_index = int(len(city_df) * 0.80)
        split_index = max(
            1, min(split_index, len(city_df) - 1)
        )

        train_parts.append(city_df.iloc[:split_index].copy())
        test_parts.append(city_df.iloc[split_index:].copy())

        print(
            f"{city}: {split_index} training rows, "
            f"{len(city_df) - split_index} testing rows"
        )

    if not train_parts or not test_parts:
        print("ERROR: Could not create train/test sets.")
        sys.exit(1)

    train_df = pd.concat(train_parts, ignore_index=True)
    test_df = pd.concat(test_parts, ignore_index=True)

    # Select input features
    excluded_columns = {
        "target_aqi_next_hour",
        "timestamp",
        "target_timestamp"
    }

    feature_columns = [
        col for col in df.columns
        if col not in excluded_columns
    ]

    X_train = train_df[feature_columns].copy()
    X_test = test_df[feature_columns].copy()

    y_train = train_df["target_aqi_next_hour"].astype(float)
    y_test = test_df["target_aqi_next_hour"].astype(float)

    # Encode city names as numeric columns
    X_train = pd.get_dummies(
        X_train, columns=["city"], dtype=int
    )

    X_test = pd.get_dummies(
        X_test, columns=["city"], dtype=int
    )

    X_test = X_test.reindex(
        columns=X_train.columns, fill_value=0
    )

    # Convert features to numeric values
    X_train = X_train.apply(
        pd.to_numeric, errors="coerce"
    )

    X_test = X_test.apply(
        pd.to_numeric, errors="coerce"
    )

    X_train = X_train.replace(
        [np.inf, -np.inf], np.nan
    )

    X_test = X_test.replace(
        [np.inf, -np.inf], np.nan
    )

    # Fill missing values using training data medians
    medians = X_train.median(numeric_only=True)

    X_train = X_train.fillna(medians).fillna(0)
    X_test = X_test.fillna(medians).fillna(0)

    print("\nTraining rows:", len(X_train))
    print("Testing rows:", len(X_test))
    print("Number of features:", X_train.shape[1])

    # Train Random Forest model
    print("\nTraining Random Forest model...")
    print("Please wait...")

    model = RandomForestRegressor(
        n_estimators=200,
        random_state=42,
        n_jobs=-1,
        min_samples_leaf=2
    )

    model.fit(X_train, y_train)

    print("Model training completed!")

    # Predict next-hour AQI
    predictions = model.predict(X_test)

    # Evaluate the model
    mae = mean_absolute_error(y_test, predictions)
    mse = mean_squared_error(y_test, predictions)
    rmse = np.sqrt(mse)

    if len(y_test) >= 2:
        r2 = r2_score(y_test, predictions)
    else:
        r2 = float("nan")

    print("\n========== MODEL EVALUATION ==========")
    print(f"MAE:  {mae:.3f}")
    print(f"MSE:  {mse:.3f}")
    print(f"RMSE: {rmse:.3f}")
    print(f"R2:   {r2:.3f}")

    # Compare against a baseline using current AQI
    if "aqi" in test_df.columns:

        baseline = pd.to_numeric(
            test_df["aqi"], errors="coerce"
        )

        valid = baseline.notna()

        if valid.any():
            baseline_mae = mean_absolute_error(
                y_test[valid], baseline[valid]
            )

            print(
                f"Baseline MAE (current AQI): "
                f"{baseline_mae:.3f}"
            )

    # Save the trained model and feature information
    model_bundle = {
        "model": model,
        "feature_columns": X_train.columns.tolist(),
        "feature_medians": medians.to_dict(),
        "target_column": "target_aqi_next_hour"
    }

    joblib.dump(model_bundle, MODEL_PATH)

    print("\nModel saved:", MODEL_PATH)

    # Save actual and predicted AQI values
    results = test_df[
        ["city", "timestamp", "target_aqi_next_hour"]
    ].copy()

    results["predicted_aqi_next_hour"] = predictions

    results["absolute_error"] = np.abs(
        results["target_aqi_next_hour"].to_numpy(dtype=float)
        - predictions
    )

    results.to_csv(PREDICTIONS_PATH, index=False)

    print("Predictions saved:", PREDICTIONS_PATH)
    print("\nAQI forecasting process completed successfully!")


if __name__ == "__main__":
    main()