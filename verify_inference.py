"""
verify_inference.py
===================
Sanity test for the FastAPI hand-off. For a sample of test-period hours it feeds ONLY the
preceding raw rows (as a FastAPI request would) into `predict_next_hour_aqi` and checks the
result matches the batch prediction saved by train_bilstm.py (reports/test_predictions.csv).
It also checks the error handling.

    python verify_inference.py --data-dir data
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from inference import predict_next_hour_aqi, get_forecaster
from train_bilstm import find_city_file
from aqi_common import CITIES


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--reports-dir", default="reports")
    ap.add_argument("--n", type=int, default=25, help="samples per city")
    a = ap.parse_args()

    preds = pd.read_csv(Path(a.reports_dir) / "test_predictions.csv", parse_dates=["timestamp"])
    worst = 0.0
    for city in CITIES:
        raw = pd.read_csv(find_city_file(Path(a.data_dir), city), parse_dates=["timestamp"])
        p = preds[preds.city == city].sample(a.n, random_state=0)
        for _, row in p.iterrows():
            hist = raw[raw.timestamp < row.timestamp].tail(72)  # data strictly BEFORE the target hour
            out = predict_next_hour_aqi(hist, city)
            assert pd.Timestamp(out["forecast_for"]) == row.timestamp, (out, row.timestamp)
            worst = max(worst, abs(out["predicted_aqi"] - row.pred_bilstm))
        print(f"[ok] {city:<10} {a.n} samples reproduce batch predictions")
    print(f"max |inference - batch| = {worst:.3f} AQI points (rounding to 0.1 expected)")
    assert worst < 0.11

    # error handling
    raw = pd.read_csv(find_city_file(Path(a.data_dir), "Delhi"))
    for label, bad_hist, city in [
        ("too little history", raw.tail(10), "Delhi"),
        ("unknown city", raw.tail(72), "Mumbai"),
        ("missing column", raw.tail(72).drop(columns=["pm25"]), "Delhi"),
        ("gap in last hours", pd.concat([raw.tail(72).iloc[:-12], raw.tail(6)]), "Delhi"),
    ]:
        try:
            predict_next_hour_aqi(bad_hist, city)
            raise SystemExit(f"[FAIL] '{label}' should have raised")
        except ValueError as e:
            print(f"[ok] {label:<20} -> ValueError: {str(e)[:70]}")
    # list-of-dict input (as parsed JSON)
    recs = raw.tail(72).to_dict(orient="records")
    print("[ok] list-of-dicts input ->", predict_next_hour_aqi(recs, "Gurgaon" if False else "Delhi"))
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
