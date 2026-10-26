
import os
import sys
import json
import pandas as pd


# --------------------------------------------------
# 1. FILE PATHS
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FORECAST_PATH = os.path.join(
    BASE_DIR, "aqi_next_hour_forecast.csv"
)

OUTPUT_PATH = os.path.join(
    BASE_DIR, "aqi_actuation_log.csv"
)

STATE_PATH = os.path.join(
    BASE_DIR, "aqi_actuator_state.json"
)


# --------------------------------------------------
# 2. CONFIGURABLE DEMO THRESHOLDS
# --------------------------------------------------

PURIFIER_ON_THRESHOLD = 100
PURIFIER_OFF_THRESHOLD = 80


# --------------------------------------------------
# 3. LOAD PREVIOUS PURIFIER STATES
# --------------------------------------------------

def load_states():

    # First, try loading the saved JSON state.
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as file:
                states = json.load(file)

            if isinstance(states, dict) and states:
                print("Purifier states loaded from JSON.")
                return states

        except (json.JSONDecodeError, OSError):
            print("WARNING: Could not read JSON state.")

    # If JSON is empty, restore states from the existing CSV log.
    if os.path.exists(OUTPUT_PATH):
        try:
            log = pd.read_csv(OUTPUT_PATH)

            required = {"city", "forecast_timestamp", "recommended_status"}

            if required.issubset(log.columns) and not log.empty:

                log["forecast_timestamp"] = pd.to_datetime(
                    log["forecast_timestamp"],
                    errors="coerce"
                )

                log = log.dropna(subset=["forecast_timestamp"])

                log = log[
                    log["recommended_status"].isin(["ON", "OFF"])
                ]

                if not log.empty:
                    log = log.sort_values("forecast_timestamp")

                    latest = log.groupby("city").tail(1)

                    states = dict(
                        zip(
                            latest["city"].astype(str),
                            latest["recommended_status"]
                        )
                    )

                    print("Purifier states restored from CSV log.")
                    return states

        except (OSError, pd.errors.ParserError) as error:
            print("WARNING: Could not restore states from CSV:", error)

    print("No previous states found. Starting with all purifiers OFF.")
    return {}


# --------------------------------------------------
# 4. SAVE PURIFIER STATES
# --------------------------------------------------

def save_states(states):

    temporary_path = STATE_PATH + ".tmp"

    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(states, file, indent=4)

    os.replace(temporary_path, STATE_PATH)


# --------------------------------------------------
# 5. DECIDE PURIFIER STATUS
# --------------------------------------------------

def decide_actuation(predicted_aqi, previous_status):

    if pd.isna(predicted_aqi):
        return previous_status, "NO CHANGE", "AQI prediction unavailable"

    if predicted_aqi >= PURIFIER_ON_THRESHOLD:

        if previous_status == "OFF":
            return (
                "ON",
                "TURN ON",
                "Predicted AQI reached ON threshold"
            )

        return (
            "ON",
            "NO CHANGE",
            "Purifier is already ON"
        )

    elif predicted_aqi <= PURIFIER_OFF_THRESHOLD:

        if previous_status == "ON":
            return (
                "OFF",
                "TURN OFF",
                "Predicted AQI reached OFF threshold"
            )

        return (
            "OFF",
            "NO CHANGE",
            "Purifier is already OFF"
        )

    else:

        return (
            previous_status,
            "NO CHANGE",
            "AQI is between thresholds; maintaining previous status"
        )


# --------------------------------------------------
# 6. MAIN SIMULATION
# --------------------------------------------------

def main():

    print("=" * 60)
    print("     IMPROVED AQI AUTOMATED ACTUATION SIMULATION")
    print("=" * 60)

    # Check forecast file
    if not os.path.exists(FORECAST_PATH):
        print("\nERROR: Forecast file not found:")
        print(FORECAST_PATH)
        print("Run aqi_predict.py first.")
        sys.exit(1)

    # Load forecasts
    forecasts = pd.read_csv(FORECAST_PATH)

    required_columns = [
        "city",
        "predicted_next_hour_aqi"
    ]

    missing = [
        column for column in required_columns
        if column not in forecasts.columns
    ]

    if missing:
        print("ERROR: Missing forecast columns:", missing)
        sys.exit(1)

    if forecasts.empty:
        print("ERROR: Forecast file is empty.")
        sys.exit(1)

    forecasts["city"] = forecasts["city"].astype(str)

    forecasts["predicted_next_hour_aqi"] = pd.to_numeric(
        forecasts["predicted_next_hour_aqi"],
        errors="coerce"
    )

    # Use forecast timestamp to identify each reading.
    # The forecast file generated by aqi_predict.py contains this column.
    if "forecast_timestamp" not in forecasts.columns:
        print("ERROR: forecast_timestamp column is missing.")
        print("Please regenerate the forecast using aqi_predict.py.")
        sys.exit(1)

    forecasts["forecast_timestamp"] = (
        pd.to_datetime(
            forecasts["forecast_timestamp"],
            errors="coerce"
        )
    )

    if forecasts["forecast_timestamp"].isna().any():
        print("ERROR: Some forecast timestamps are invalid.")
        sys.exit(1)

    # Each city should have one record per forecast timestamp.
    forecasts = forecasts.drop_duplicates(
        subset=["city", "forecast_timestamp"],
        keep="last"
    )

    # Load saved purifier statuses.
    states = load_states()

    # Load old log, if it exists.
    if os.path.exists(OUTPUT_PATH):
        try:
            old_log = pd.read_csv(OUTPUT_PATH)

            if not {
                "city",
                "forecast_timestamp"
            }.issubset(old_log.columns):
                print("WARNING: Existing log has an unexpected format.")
                print("A new log will be created.")
                old_log = pd.DataFrame()

        except (OSError, pd.errors.ParserError):
            print("WARNING: Existing log could not be read.")
            old_log = pd.DataFrame()

    else:
        old_log = pd.DataFrame()

    # Identify forecasts that have already been processed.
    processed = set()

    if not old_log.empty:

        old_log["city"] = old_log["city"].astype(str)

        old_log["forecast_timestamp"] = (
            pd.to_datetime(
                old_log["forecast_timestamp"],
                errors="coerce"
            )
        )

        for _, old_row in old_log.iterrows():

            old_time = old_row["forecast_timestamp"]

            if pd.notna(old_time):
                processed.add(
                    (
                        old_row["city"],
                        old_time.strftime("%Y-%m-%d %H:%M:%S")
                    )
                )

    new_records = []

    print("\nDemo thresholds:")
    print(
        f"Purifier ON at AQI >= {PURIFIER_ON_THRESHOLD}"
    )
    print(
        f"Purifier OFF at AQI <= {PURIFIER_OFF_THRESHOLD}"
    )

    print("\nProcessing forecasts...\n")

    # Process forecasts in chronological order.
    forecasts = forecasts.sort_values(
        ["forecast_timestamp", "city"]
    )

    for _, row in forecasts.iterrows():

        city = row["city"]
        predicted_aqi = row["predicted_next_hour_aqi"]

        forecast_time = row["forecast_timestamp"]

        timestamp_key = forecast_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        record_key = (city, timestamp_key)

        # Avoid processing the exact same forecast twice.
        if record_key in processed:
            print(
                f"{city} | {timestamp_key} | "
                "Already processed; skipping duplicate."
            )
            continue

        # Restore previous state, or default to OFF.
        previous_status = states.get(city, "OFF")

        if previous_status not in ("ON", "OFF"):
            previous_status = "OFF"

        # Make the actuation decision.
        status, action, reason = decide_actuation(
            predicted_aqi,
            previous_status
        )

        # Save the new state in memory.
        states[city] = status

        record = {
            "city": city,
            "forecast_timestamp": timestamp_key,
            "predicted_next_hour_aqi": predicted_aqi,
            "previous_status": previous_status,
            "recommended_status": status,
            "simulated_action": action,
            "decision_reason": reason
        }

        new_records.append(record)
        processed.add(record_key)

        # Display decision.
        print("-" * 50)
        print("City:", city)
        print("Forecast time:", timestamp_key)

        if pd.isna(predicted_aqi):
            print("Predicted AQI: unavailable")
        else:
            print(f"Predicted AQI: {predicted_aqi:.2f}")

        print("Previous status:", previous_status)
        print("Recommended status:", status)
        print("Action:", action)
        print("Reason:", reason)

    # Save states even when all forecasts were already processed.
    save_states(states)

    # Append only new decisions to the log.
    if new_records:

        new_log = pd.DataFrame(new_records)

        if old_log.empty:
            combined_log = new_log
        else:
            combined_log = pd.concat(
                [old_log, new_log],
                ignore_index=True
            )

        combined_log.to_csv(
            OUTPUT_PATH,
            index=False
        )

        print("\nNew decisions saved:", len(new_records))

    else:
        print("\nNo new forecasts to process.")
        print("Existing log has not been changed.")

    print("\n" + "=" * 60)
    print("       SIMULATION COMPLETED")
    print("=" * 60)

    print("\nSaved purifier states:")
    print(json.dumps(states, indent=4))

    print("\nState file:")
    print(STATE_PATH)

    print("\nDecision log:")
    print(OUTPUT_PATH)

    print("\nNOTE: This is software simulation only.")
    print("No physical device has been controlled.")


# --------------------------------------------------
# 7. RUN PROGRAM
# --------------------------------------------------

if __name__ == "__main__":
    main()
