"""
existing_work_compare.py
========================
Compares our Bi-LSTM with the model families used by
https://github.com/Okes2024/Air-Quality-Index-Prediction-Using-ML-and-IoT-Sensor-Data
(Ridge, RandomForest, GradientBoosting) in two controlled ways:

  --part forecast : THEIR models, OUR task/protocol
                    (next-hour AQI forecast, chronological split, same windows as the Bi-LSTM)
  --part nowcast  : THEIR task/protocol, OUR data
                    (estimate the SAME hour's AQI from that hour's pollutants + hour/dow,
                     random 75/25 split, as in their script)

    python existing_work_compare.py --part forecast --data-dir data
    python existing_work_compare.py --part nowcast  --data-dir data
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from aqi_common import CITIES, POLLUTANTS, TARGET, build_features, feature_names
from train_bilstm import find_city_file, make_windows

SEED = 42


def sc(y, p):
    return {"MAE": float(mean_absolute_error(y, p)), "RMSE": float(np.sqrt(mean_squared_error(y, p))),
            "R2": float(r2_score(y, p)), "n_test": int(len(y))}


def their_models():
    return {"Ridge": Ridge(), "RandomForest": RandomForestRegressor(n_estimators=100, min_samples_leaf=2, n_jobs=-1, random_state=SEED),
            "GradientBoosting": GradientBoostingRegressor(random_state=SEED)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["forecast", "nowcast"], required=True)
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--model-dir", default="models")
    ap.add_argument("--out-dir", default="reports")
    a = ap.parse_args()
    model_dir, out = Path(a.model_dir), Path(a.out_dir)
    meta = json.loads((model_dir / "bilstm_aqi_metadata.json").read_text())
    bundle = joblib.load(model_dir / "bilstm_aqi_scaler.joblib")
    window, extra = meta["window_hours"], meta["extra_cols"]
    FEATURES, CONT = feature_names(extra)
    t_val, t_test = pd.Timestamp(meta["split"]["train_end_exclusive"]), pd.Timestamp(meta["split"]["val_end_exclusive"])
    scaler = bundle["feature_scaler"]
    cont_idx = [FEATURES.index(c) for c in CONT]
    res = {}

    if a.part == "forecast":
        Xs, ys, ts = [], [], []
        for city in CITIES:
            df = pd.read_csv(find_city_file(Path(a.data_dir), city))
            f, imputed = build_features(df, city, extra)
            F = f[FEATURES].values.astype("float64").copy()
            F[:, cont_idx] = (F[:, cont_idx] - scaler.mean_) / scaler.scale_
            ok_t = (~imputed.values) & ~np.isnan(f[TARGET].values)
            X, y, t, _ = make_windows(F, f[TARGET].values, ok_t, f.index, window, 1)
            Xs.append(X[:, -1, :]); ys.append(y); ts.append(t)
        X, y, t = np.concatenate(Xs), np.concatenate(ys), pd.DatetimeIndex(np.concatenate(ts))
        tr, te = t < t_val, t >= t_test
        for name, m in their_models().items():
            m.fit(X[tr], y[tr])
            res[name] = sc(y[te], np.clip(m.predict(X[te]), 0, 500))
            print("forecast", name, res[name], flush=True)
        (out / "existing_forecast_protocol.json").write_text(json.dumps(res, indent=2))
    else:
        rows = []
        for city in CITIES:
            df = pd.read_csv(find_city_file(Path(a.data_dir), city), parse_dates=["timestamp"])
            d = df[["timestamp"] + POLLUTANTS + [TARGET]].dropna().copy()
            d["hour"], d["dow"] = d.timestamp.dt.hour, d.timestamp.dt.dayofweek
            for c in CITIES: d[f"city_{c}"] = float(c == city)
            rows.append(d)
        d = pd.concat(rows)
        feats = POLLUTANTS + ["hour", "dow"] + [f"city_{c}" for c in CITIES]  # their feature idea; AQI itself NOT an input
        Xtr, Xte, ytr, yte = train_test_split(d[feats].values, d[TARGET].values, test_size=0.25, random_state=SEED)
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        for name, m in their_models().items():
            m.fit((Xtr - mu) / sd, ytr)
            res[name] = sc(yte, np.clip(m.predict((Xte - mu) / sd), 0, 500))
            print("nowcast", name, res[name], flush=True)
        (out / "existing_nowcast_protocol.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
