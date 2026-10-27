import os
import sys
import json
import joblib
import numpy as np
import pandas as pd


# ==================================================
# 1. FILE PATHS
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATASET_PATH = os.path.join(
    BASE_DIR, "aqi_next_hour_dataset.csv"
)

MODEL_PATH = os.path.join(
    BASE_DIR, "aqi_forecasting_model.joblib"
)

FORECAST_PATH = os.path.join(
    BASE_DIR, "aqi_next_hour_forecast.csv"
)

ACTUATION_LOG_PATH = os.path.join(
    BASE_DIR, "aqi_actuation_log.csv"
)

STATE_PATH = os.path.join(
    BASE_DIR, "aqi_actuator_state.json"
)


# ==================================================
# 2. DEMONSTRATION THRESHOLDS
# ==================================================

PURIFIER_ON_THRESHOLD = 100
PURIFIER_OFF_THRESHOLD = 80


# ==================================================
# 3. LOAD SAVED STATES
# ==================================================

def load_states():

    # Try to load the JSON state file first.
    if os.path.exists(STATE_PATH):

        try:
            with open(STATE_PATH, "r", encoding="utf-8") as file:
                states = json.load(file)

            if isinstance(states, dict):
                return states

        except (OSError, json.JSONDecodeError):
            print("Warning: Could not read state file.")

    # Restore states from the latest actuation log entries.
    if os.path.exists(ACTUATION_LOG_PATH):

        try:
            log = pd.read_csv(ACTUATION_LOG_PATH)

            required = {
                "city",
                "forecast_timestamp",
                "recommended_status"
            }

            if required.issubset(log.columns) and not log.empty:

                log["forecast_timestamp"] = pd.to_datetime(
                    log["forecast_timestamp"],
                    errors="coerce"
                )

                log = log.dropna(
                    subset=["forecast_timestamp"]
                )

                log = log[
                    log["recommended_status"].isin(["ON", "OFF"])
                ]

                log = log.sort_values("forecast_timestamp")

                latest = log.groupby("city").tail(1)

                return dict(
                    zip(
                        latest["city"].astype(str),
                        latest["recommended_status"]
                    )
                )

        except (OSError, pd.errors.ParserError):
            print("Warning: Could not restore state from log.")

    return {}


# ==================================================
# 4. SAVE STATES
# ==================================================

def save_states(states):

    temporary_path = STATE_PATH + ".tmp"

    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(states, file, indent=4)

    os.replace(temporary_path, STATE_PATH)


# ==================================================
# 5. ACTUATION DECISION
# ==================================================

def decide_actuation(predicted_aqi, previous_status):

    if pd.isna(predicted_aqi):
        return previous_status, "NO CHANGE", "AQI prediction unavailable"

    if predicted_aqi >= PURIFIER_ON_THRESHOLD:

        if previous_status == "OFF":
            return "ON", "TURN ON", "AQI reached ON threshold"

        return "ON", "NO CHANGE", "Purifier is already ON"

    if predicted_aqi <= PURIFIER_OFF_THRESHOLD:

        if previous_status == "ON":
            return "OFF", "TURN OFF", "AQI reached OFF threshold"

        return "OFF", "NO CHANGE", "Purifier is already OFF"

    return (
        previous_status,
        "NO CHANGE",
        "AQI is between thresholds; maintaining previous status"
    )


# ==================================================
# 6. LOAD MODEL AND DATASET
# ==================================================

def main():

    print("=" * 60)
    print("       AI-BASED AQI FORECASTING SYSTEM")
    print("=" * 60)

    if not os.path.exists(MODEL_PATH):
        print("ERROR: Trained model not found:", MODEL_PATH)
        print("Run aqi_train_model.py first.")
        sys.exit(1)

    if not os.path.exists(DATASET_PATH):
        print("ERROR: Dataset not found:", DATASET_PATH)
        sys.exit(1)

    print("\nLoading trained model...")

    bundle = joblib.load(MODEL_PATH)

    model = bundle["model"]
    feature_columns = bundle["feature_columns"]
    feature_medians = bundle["feature_medians"]

    print("Model loaded.")

    print("\nLoading dataset...")

    df = pd.read_csv(DATASET_PATH)

    required = [
        "city",
        "timestamp",
        "target_aqi_next_hour"
    ]

    missing = [col for col in required if col not in df.columns]

    if missing:
        print("ERROR: Missing dataset columns:", missing)
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

    if df.empty:
        print("ERROR: No usable dataset rows.")
        sys.exit(1)

    # Select the latest record for each city.
    latest = (
        df.groupby("city", sort=True)
        .tail(1)
        .copy()
        .reset_index(drop=True)
    )

    print("Latest records selected:", len(latest))


    # ==================================================
    # 7. PREPARE MODEL FEATURES
    # ==================================================

    excluded = {
        "target_aqi_next_hour",
        "timestamp",
        "target_timestamp"
    }

    input_columns = [
        col for col in df.columns
        if col not in excluded
    ]

    X = latest[input_columns].copy()

    X = pd.get_dummies(
        X, columns=["city"], dtype=int
    )

    # Ensure the same feature schema as training.
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


    # ==================================================
    # 8. PREDICT NEXT-HOUR AQI
    # ==================================================

    print("\nGenerating next-hour AQI predictions...")

    predictions = model.predict(X)

    forecast = pd.DataFrame({
        "city": latest["city"].to_numpy(),
        "latest_timestamp": latest["timestamp"].to_numpy(),
        "predicted_next_hour_aqi": predictions
    })

    forecast["forecast_timestamp"] = (
        pd.to_datetime(forecast["latest_timestamp"])
        + pd.Timedelta(hours=1)
    )

    # Save the latest forecast results.
    forecast.to_csv(
        FORECAST_PATH,
        index=False
    )

    print("\nForecast results:")
    print(forecast.to_string(index=False))


    # ==================================================
    # 9. SIMULATE ACTUATION
    # ==================================================

    print("\nApplying actuation rules...")

    states = load_states()

    new_log_records = []

    for _, row in forecast.iterrows():

        city = str(row["city"])
        predicted_aqi = row["predicted_next_hour_aqi"]

        forecast_time = pd.Timestamp(
            row["forecast_timestamp"]
        )

        timestamp_key = forecast_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        previous_status = states.get(city, "OFF")

        if previous_status not in ("ON", "OFF"):
            previous_status = "OFF"

        status, action, reason = decide_actuation(
            predicted_aqi,
            previous_status
        )

        states[city] = status

        new_log_records.append({
            "city": city,
            "forecast_timestamp": timestamp_key,
            "predicted_next_hour_aqi": predicted_aqi,
            "previous_status": previous_status,
            "recommended_status": status,
            "simulated_action": action,
            "decision_reason": reason
        })

        print("\nCity:", city)
        print(f"Predicted AQI: {predicted_aqi:.2f}")
        print("Previous status:", previous_status)
        print("Recommended status:", status)
        print("Action:", action)
        print("Reason:", reason)


    # ==================================================
    # 10. SAVE RESULTS AND STATES
    # ==================================================

    save_states(states)

    new_log = pd.DataFrame(new_log_records)

    if os.path.exists(ACTUATION_LOG_PATH):

        try:
            old_log = pd.read_csv(ACTUATION_LOG_PATH)

            # Avoid adding duplicate city/timestamp entries.
            if {
                "city",
                "forecast_timestamp"
            }.issubset(old_log.columns):

                old_keys = set(
                    zip(
                        old_log["city"].astype(str),
                        old_log["forecast_timestamp"].astype(str)
                    )
                )

                new_log = new_log[
                    ~new_log.apply(
                        lambda row: (
                            str(row["city"]),
                            str(row["forecast_timestamp"])
                        ) in old_keys,
                        axis=1
                    )
                ]

                combined_log = pd.concat(
                    [old_log, new_log],
                    ignore_index=True
                )

            else:
                combined_log = new_log

        except (OSError, pd.errors.ParserError):
            combined_log = new_log

    else:
        combined_log = new_log

    combined_log.to_csv(
        ACTUATION_LOG_PATH,
        index=False
    )

    print("\n" + "=" * 60)
    print("       SYSTEM RUN COMPLETED")
    print("=" * 60)

    print("\nForecast file:")
    print(FORECAST_PATH)

    print("\nActuation log:")
    print(ACTUATION_LOG_PATH)

    print("\nSaved states:")
    print(json.dumps(states, indent=4))

    print("\nNOTE: Software simulation only.")
    print("No physical device has been controlled.")


# ==================================================
# 11. START PROGRAM
# ==================================================

if __name__ == "__main__":
    main()
