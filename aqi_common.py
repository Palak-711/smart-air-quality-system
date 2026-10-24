"""
aqi_common.py
=============
Constants and feature engineering shared by BOTH training (train_bilstm.py) and
serving (inference.py). Keeping a single implementation guarantees that the
features the model sees in production are computed exactly as they were in
training (no train/serve skew).

Leakage rules baked in here:
  * every rolling / diff feature is CAUSAL (uses only the current and past rows),
  * missing hours are filled with a forward-fill only (never interpolated from
    the future), capped at MAX_FFILL hours,
  * time features are derived from the timestamp itself, so inference only needs
    the timestamp + sensor readings.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CITIES = ["Delhi", "Faridabad", "Gurugram"]
CITY_ALIASES = {
    "delhi": "Delhi",
    "new delhi": "Delhi",
    "faridabad": "Faridabad",
    "gurugram": "Gurugram",
    "gurgaon": "Gurugram",  # the raw CSV labels Gurugram as "Gurgaon"
}

POLLUTANTS = ["pm25", "pm10", "no2", "o3", "co", "so2"]
OPTIONAL_WEATHER = ["temperature", "humidity"]  # used automatically if present in every city file
TARGET = "aqi"

ROLL_WINDOWS = (3, 6, 24)
MAX_ROLL = max(ROLL_WINDOWS)
MAX_FFILL = 3  # longest run of missing hours that will be forward-filled


def normalize_city(name: str) -> str:
    key = str(name).strip().lower()
    if key not in CITY_ALIASES:
        raise ValueError(f"Unknown city '{name}'. Supported: {CITIES}")
    return CITY_ALIASES[key]


def aqi_category(value: float) -> str:
    """Indian CPCB AQI categories (matches the `aqi_category` column in the CSVs)."""
    if value <= 50:
        return "Good"
    if value <= 100:
        return "Satisfactory"
    if value <= 200:
        return "Moderate"
    if value <= 300:
        return "Poor"
    if value <= 400:
        return "Very Poor"
    return "Severe"


def feature_names(extra_cols=()) -> tuple[list[str], list[str]]:
    """Return (all_feature_names, continuous_feature_names).

    Only the continuous features are standardised; cyclical, binary and one-hot
    features are already in [-1, 1] / {0, 1} and are passed through unscaled.
    """
    base = POLLUTANTS + list(extra_cols) + [TARGET]
    rolled = [f"aqi_roll{w}" for w in ROLL_WINDOWS] + [f"pm25_roll{w}" for w in ROLL_WINDOWS]
    continuous = base + rolled + ["aqi_diff1"]
    cyclical = ["hour_sin", "hour_cos", "dow_sin", "dow_cos", "doy_sin", "doy_cos", "is_weekend"]
    city_cols = [f"city_{c}" for c in CITIES]
    return continuous + cyclical + city_cols, continuous


def regularize_hourly(df: pd.DataFrame, value_cols: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    """Put a city's data on a strict hourly grid.

    Returns (frame, imputed_mask). `imputed_mask` is True for any hour that was
    missing (or had NaNs) in the raw data; those hours are forward-filled (causal)
    for up to MAX_FFILL hours, and are never used as prediction targets.
    """
    d = df.copy()
    d["timestamp"] = pd.to_datetime(d["timestamp"])
    d = d.sort_values("timestamp").drop_duplicates("timestamp", keep="last").set_index("timestamp")
    full = pd.date_range(d.index.min(), d.index.max(), freq="h")
    d = d.reindex(full)
    imputed = d[value_cols].isna().any(axis=1)
    d[value_cols] = d[value_cols].astype(float).ffill(limit=MAX_FFILL)
    d.index.name = "timestamp"
    return d, imputed


def build_features(df: pd.DataFrame, city: str, extra_cols=()) -> tuple[pd.DataFrame, pd.Series]:
    """Raw city dataframe -> (feature frame on an hourly grid, imputed mask).

    The feature frame has one row per hour; rows whose causal rolling windows are
    not yet full (first MAX_ROLL-1 hours) or sit inside a long gap contain NaN and
    are skipped when windows are built.
    """
    city = normalize_city(city)
    value_cols = POLLUTANTS + list(extra_cols) + [TARGET]
    missing = [c for c in ["timestamp"] + value_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {missing}")

    d, imputed = regularize_hourly(df, value_cols)
    f = d[value_cols].copy()

    for w in ROLL_WINDOWS:  # causal rolling means (window ends at the current hour)
        f[f"aqi_roll{w}"] = f[TARGET].rolling(w, min_periods=w).mean()
        f[f"pm25_roll{w}"] = f["pm25"].rolling(w, min_periods=w).mean()
    f["aqi_diff1"] = f[TARGET].diff()

    idx = f.index
    hour, dow, doy = idx.hour.values, idx.dayofweek.values, idx.dayofyear.values
    f["hour_sin"], f["hour_cos"] = np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)
    f["dow_sin"], f["dow_cos"] = np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7)
    f["doy_sin"], f["doy_cos"] = np.sin(2 * np.pi * doy / 366), np.cos(2 * np.pi * doy / 366)
    f["is_weekend"] = (dow >= 5).astype(float)
    for c in CITIES:
        f[f"city_{c}"] = float(c == city)

    all_features, _ = feature_names(extra_cols)
    return f[all_features], imputed
