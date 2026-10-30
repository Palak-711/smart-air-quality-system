"""
inference_subhourly.py  --  15- and 30-minute AQI forecasts (model trained on SIMULATED 15-minute data)
=======================================================================================================
    from inference_subhourly import predict_15_30min
    predict_15_30min(history15, city="Delhi")

`history15`: recent 15-MINUTE readings (DataFrame or list of dicts) with columns
    timestamp, pm25, pm10, no2, o3, co, so2, aqi
At least `min_history_steps` (119 = about 30 hours) rows on a 15-minute grid, ending at the forecast origin.
The model was trained with origins at the top of the hour (minute 00); other minutes work but get a warning.

If you only have HOURLY data (our CSVs) use `simulate_history_from_hourly()` to create a simulated 15-minute history.
The output is flagged "simulated_training_data": true -- 15/30-minute accuracy is not validated on real sensor data.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from aqi_common import aqi_category, normalize_city
from subhourly import STEP_MIN, VALUE_COLS, build_features_15min, regularize_15min, simulate_15min

MODEL_FILE, SCALER_FILE, META_FILE = "bilstm_aqi_15_30min.keras", "bilstm_aqi_15_30min_scaler.joblib", "bilstm_aqi_15_30min_metadata.json"


class SubHourlyForecaster:
    def __init__(self, model_dir=None):
        d = Path(model_dir or os.environ.get("AQI_MODEL_DIR") or Path(__file__).resolve().parent / "models")
        from tensorflow import keras

        self.model = keras.models.load_model(d / MODEL_FILE, compile=False)
        b = joblib.load(d / SCALER_FILE); meta = json.loads((d / META_FILE).read_text())
        self.scaler, self.features, self.continuous = b["feature_scaler"], b["features"], b["continuous_cols"]
        self.y_mean, self.y_std = b["target_mean"], b["target_std"]
        self.window, self.min_history = meta["window_steps"], meta["min_history_steps"]
        self.horizons = meta["horizons_minutes"]
        self._ci = [self.features.index(c) for c in self.continuous]

    def predict(self, history15, city: str) -> dict:
        df = pd.DataFrame(history15) if not isinstance(history15, pd.DataFrame) else history15
        missing = [c for c in ["timestamp"] + VALUE_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required column(s): {missing}")
        city = normalize_city(city)
        if len(df) < self.min_history:
            raise ValueError(f"Need at least {self.min_history} readings at 15-minute spacing, got {len(df)}")
        f = build_features_15min(regularize_15min(df), city)
        win = f.iloc[-self.window:]
        if len(win) < self.window or win.isna().any().any():
            raise ValueError("The last readings must be a continuous 15-minute series (gaps over 3 hours are not allowed)")
        x = win.values.astype("float64"); x[:, self._ci] = (x[:, self._ci] - self.scaler.mean_) / self.scaler.scale_
        p = np.clip(self.model(x[None].astype("float32"), training=False).numpy().ravel() * self.y_std + self.y_mean, 0, 500)
        t = f.index[-1]
        out = {"city": city, "as_of": str(t), "simulated_training_data": True,
               "forecasts": [{"minutes_ahead": m, "forecast_for": str(t + pd.Timedelta(minutes=m)),
                              "predicted_aqi": round(float(v), 1), "aqi_category": aqi_category(v)} for m, v in zip(self.horizons, p)]}
        if t.minute != 0:
            out["warning"] = "model was trained with forecast origins at minute 00; accuracy at other minutes is untested"
        return out


_single = None


def predict_15_30min(history15, city: str, model_dir=None) -> dict:
    global _single
    if _single is None:
        _single = SubHourlyForecaster(model_dir)
    return _single.predict(history15, city)


def simulate_history_from_hourly(df_hourly: pd.DataFrame, n_hours: int = 72, seed: int = 42) -> pd.DataFrame:
    """Hourly readings -> SIMULATED 15-minute history (last n_hours hours); for demos when no 15-minute sensor data exists."""
    return simulate_15min(df_hourly.tail(n_hours), seed=seed).reset_index()[["timestamp"] + VALUE_COLS]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hourly-csv", required=True, help="hourly city CSV; a 15-minute history is SIMULATED from its last 72 rows")
    ap.add_argument("--city", required=True)
    ap.add_argument("--model-dir", default=None)
    a = ap.parse_args()
    print(json.dumps(predict_15_30min(simulate_history_from_hourly(pd.read_csv(a.hourly_csv)), a.city, a.model_dir), indent=2))
