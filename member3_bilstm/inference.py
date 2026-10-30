"""
inference.py  --  next-hour AQI prediction for FastAPI (Member 5)
================================================================
    from inference import predict_next_hour_aqi

    result = predict_next_hour_aqi(history, city="Delhi")
    # {'city': 'Delhi', 'as_of': '2023-12-31 23:00:00',
    #  'forecast_for': '2024-01-01 00:00:00', 'horizon_hours': 1,
    #  'predicted_aqi': 212.4, 'aqi_category': 'Poor'}

`history` = the most recent HOURLY readings for that city, as a DataFrame or a list
of dicts (e.g. a parsed JSON body) with columns:
    timestamp, pm25, pm10, no2, o3, co, so2, aqi   (+ temperature, humidity if the
    model was trained with them -- see models/bilstm_aqi_metadata.json "extra_cols")
At least `min_history_hours` (47 by default) consecutive hours are needed: 24 for
the model window plus 23 so the 24-hour rolling features are fully warmed up, exactly
as in training. Rows may be supplied in any order; short gaps (<=3h) are forward-filled.

The model and scaler are loaded ONCE (module-level singleton), so FastAPI requests only
pay for the forward pass. Errors are raised as ValueError (map to HTTP 422).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from aqi_common import TARGET, aqi_category, build_features, normalize_city

MODEL_FILE = "bilstm_aqi_1h.keras"
SCALER_FILE = "bilstm_aqi_scaler.joblib"
META_FILE = "bilstm_aqi_metadata.json"


class AQIForecaster:
    def __init__(self, model_dir: str | os.PathLike | None = None):
        model_dir = Path(model_dir or os.environ.get("AQI_MODEL_DIR") or Path(__file__).resolve().parent / "models")
        from tensorflow import keras  # imported lazily: keeps `import inference` cheap

        self.model = keras.models.load_model(model_dir / MODEL_FILE, compile=False)
        bundle = joblib.load(model_dir / SCALER_FILE)
        meta = json.loads((model_dir / META_FILE).read_text())
        self.scaler = bundle["feature_scaler"]
        self.features: list[str] = bundle["features"]
        self.continuous: list[str] = bundle["continuous_cols"]
        self.y_mean, self.y_std = bundle["target_mean"], bundle["target_std"]
        self.window: int = meta["window_hours"]
        self.extra_cols: list[str] = meta["extra_cols"]
        self.min_history: int = meta["min_history_hours"]
        self._cont_idx = [self.features.index(c) for c in self.continuous]

    # ------------------------------------------------------------------
    def _prepare(self, history, city: str):
        df = pd.DataFrame(history) if not isinstance(history, pd.DataFrame) else history
        if df.empty:
            raise ValueError("history is empty")
        city = normalize_city(city)
        if len(df) < self.min_history:
            raise ValueError(f"Need at least {self.min_history} hourly readings, got {len(df)}")

        feats, _ = build_features(df, city, self.extra_cols)  # same code path as training
        win = feats.iloc[-self.window:]
        if len(win) < self.window or win.isna().any().any():
            raise ValueError(
                f"The last {self.min_history} hours must be consecutive hourly readings "
                "(gaps longer than 3 hours or missing values are not allowed)."
            )
        x = win[self.features].values.astype("float64")
        x[:, self._cont_idx] = (x[:, self._cont_idx] - self.scaler.mean_) / self.scaler.scale_
        return x[None].astype("float32"), feats.index[-1], city, float(feats[TARGET].iloc[-1])

    def predict(self, history, city: str) -> dict:
        x, last_ts, city, _ = self._prepare(history, city)
        p = float(self.model(x, training=False).numpy().ravel()[0]) * self.y_std + self.y_mean
        p = float(np.clip(p, 0.0, 500.0))
        return {
            "city": city,
            "as_of": str(last_ts),
            "forecast_for": str(last_ts + pd.Timedelta(hours=1)),
            "horizon_hours": 1,
            "predicted_aqi": round(p, 1),
            "aqi_category": aqi_category(p),
        }

    def predict_horizons(self, history, city: str, horizons_minutes=(15, 30, 60)) -> dict:
        """AQI forecasts at several horizons up to 60 minutes.

        * 60 min : the trained Bi-LSTM forecast (validated: see README metrics).
        * <60 min: LINEAR INTERPOLATION between the last observed AQI and the 60-minute
                   forecast. The training data is hourly, so there is no ground truth at
                   15/30 minutes: these values are estimates and are NOT validated.
        """
        bad = [m for m in horizons_minutes if not (0 < m <= 60)]
        if bad:
            raise ValueError(f"horizons_minutes must be between 1 and 60, got {bad}")
        x, last_ts, city, last_aqi = self._prepare(history, city)
        p60 = float(np.clip(float(self.model(x, training=False).numpy().ravel()[0]) * self.y_std + self.y_mean, 0.0, 500.0))
        out = []
        for m in sorted(set(horizons_minutes)):
            v = p60 if m == 60 else last_aqi + (m / 60.0) * (p60 - last_aqi)
            out.append({
                "minutes_ahead": m,
                "forecast_for": str(last_ts + pd.Timedelta(minutes=m)),
                "predicted_aqi": round(float(v), 1),
                "aqi_category": aqi_category(v),
                "method": "bilstm" if m == 60 else "linear_interpolation",
                "validated": m == 60,
            })
        return {"city": city, "as_of": str(last_ts), "last_observed_aqi": round(last_aqi, 1), "forecasts": out}


_singleton: AQIForecaster | None = None


def get_forecaster(model_dir=None) -> AQIForecaster:
    """Load once, reuse for every request (call this in FastAPI's startup/lifespan)."""
    global _singleton
    if _singleton is None:
        _singleton = AQIForecaster(model_dir)
    return _singleton


def predict_next_hour_aqi(history, city: str, model_dir=None) -> dict:
    """Convenience wrapper: forecast AQI for the hour after the last row of `history`."""
    return get_forecaster(model_dir).predict(history, city)


def predict_aqi_horizons(history, city: str, horizons_minutes=(15, 30, 60), model_dir=None) -> dict:
    """Convenience wrapper for 15 / 30 / 60-minute forecasts (see AQIForecaster.predict_horizons)."""
    return get_forecaster(model_dir).predict_horizons(history, city, horizons_minutes)


if __name__ == "__main__":  # quick CLI smoke test
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="a city CSV; the last 72 rows are used as history")
    ap.add_argument("--city", required=True)
    ap.add_argument("--model-dir", default=None)
    ap.add_argument("--horizons", type=int, nargs="*", default=None,
                    help="minutes ahead, e.g. --horizons 15 30 60 (values below 60 are interpolated estimates)")
    a = ap.parse_args()
    hist = pd.read_csv(a.csv).tail(72)
    if a.horizons:
        print(json.dumps(predict_aqi_horizons(hist, a.city, tuple(a.horizons), a.model_dir), indent=2))
    else:
        print(json.dumps(predict_next_hour_aqi(hist, a.city, a.model_dir), indent=2))
    print("(actual AQI of the last supplied hour:", round(float(hist[TARGET].iloc[-1]), 1), ")")
