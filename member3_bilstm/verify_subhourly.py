"""Check that inference_subhourly reproduces the batch predictions saved by train_subhourly.py."""
import argparse
from pathlib import Path
import pandas as pd
from inference_subhourly import predict_15_30min
from subhourly import VALUE_COLS

ap = argparse.ArgumentParser(); ap.add_argument("--reports-dir", default="reports"); ap.add_argument("--n", type=int, default=20)
a = ap.parse_args(); R = Path(a.reports_dir)
preds = pd.read_csv(R / "subhourly_test_predictions.csv", parse_dates=["origin"])
worst = 0.0
for city in ["Delhi", "Faridabad", "Gurugram"]:
    sim = pd.read_csv(R / "simulated_15min" / f"{city.lower()}_15min_SIMULATED.csv", parse_dates=["timestamp"])
    for _, r in preds[preds.city == city].sample(a.n, random_state=0).iterrows():
        out = predict_15_30min(sim[sim.timestamp <= r.origin].tail(150)[["timestamp"] + VALUE_COLS], city)
        f15, f30 = out["forecasts"]
        worst = max(worst, abs(f15["predicted_aqi"] - r.pred_15min), abs(f30["predicted_aqi"] - r.pred_30min))
    print(f"[ok] {city}")
print(f"max |inference - batch| = {worst:.3f} (rounding to 0.1 expected)"); assert worst < 0.11
for label, bad in [("too little history", sim.tail(10)), ("missing column", sim.tail(150).drop(columns=["pm25"]))]:
    try: predict_15_30min(bad[["timestamp"] + [c for c in VALUE_COLS if c in bad.columns]], "Delhi"); raise SystemExit(f"FAIL: {label}")
    except ValueError as e: print(f"[ok] {label} -> ValueError")
print("ALL CHECKS PASSED")
