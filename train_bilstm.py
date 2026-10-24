"""
train_bilstm.py  --  Member 3: Bi-LSTM 1-hour-ahead AQI forecaster
===================================================================
One shared model for Delhi, Faridabad and Gurugram (city one-hot as an input).

Pipeline
  1. load each city's calibrated CSV, put it on a strict hourly grid
  2. causal feature engineering (aqi_common.build_features)
  3. CHRONOLOGICAL split by calendar time (same cut-offs for every city)
  4. fit scalers on TRAIN rows only
  5. build sliding windows: last `window` hours -> AQI at t+1
       - a window's target decides which split it belongs to
       - val/test inputs may look back into earlier periods (that is only past
         data, exactly what production sees); no future information is used
  6. train Bi-LSTM (early stopping on the validation split)
  7. evaluate on the untouched test split: MAE / RMSE / R^2, next to baselines
  8. save model (.keras), scaler bundle (.joblib), metadata (.json), reports

Usage
  python train_bilstm.py --data-dir data --out-dir models --reports-dir reports
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

from aqi_common import CITIES, OPTIONAL_WEATHER, POLLUTANTS, TARGET, MAX_ROLL, build_features, feature_names

MODEL_FILE = "bilstm_aqi_1h.keras"
SCALER_FILE = "bilstm_aqi_scaler.joblib"
META_FILE = "bilstm_aqi_metadata.json"


# --------------------------------------------------------------------------- data
def find_city_file(data_dir: Path, city: str) -> Path:
    """Pick the CSV for a city by filename (prefers files containing 'calibrated')."""
    prefixes = [city.lower()] + (["gurgaon"] if city == "Gurugram" else [])
    cands = [p for p in data_dir.glob("*.csv") if any(p.name.lower().startswith(x) for x in prefixes)]
    if not cands:
        raise FileNotFoundError(f"No CSV starting with '{city.lower()}' found in {data_dir}")
    cands.sort(key=lambda p: ("calibrated" not in p.name.lower(), p.name))
    return cands[0]


def set_seeds(seed: int) -> None:
    import tensorflow as tf

    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def make_windows(F: np.ndarray, y: np.ndarray, ok_target: np.ndarray, times: pd.DatetimeIndex,
                 window: int, horizon: int):
    """Vectorised sliding windows. A sample is kept only if every input row is
    NaN-free and the target hour is a real (non-imputed) observation."""
    n = len(F)
    ok_row = ~np.isnan(F).any(axis=1)
    ends = np.arange(window - 1, n - horizon)
    starts = ends - window + 1
    bad_cum = np.concatenate([[0], np.cumsum(~ok_row)])
    keep = ((bad_cum[ends + 1] - bad_cum[starts]) == 0) & ok_target[ends + horizon]
    ends = ends[keep]
    idx = ends[:, None] + np.arange(-window + 1, 1)[None, :]
    return F[idx], y[ends + horizon], times[ends + horizon], y[ends]


# ------------------------------------------------------------------------ metrics
def score(y_true, y_pred) -> dict:
    return {
        "MAE": round(float(mean_absolute_error(y_true, y_pred)), 3),
        "RMSE": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 3),
        "R2": round(float(r2_score(y_true, y_pred)), 4),
        "n": int(len(y_true)),
    }


def score_by_city(y_true, y_pred, city_arr) -> dict:
    out = {"overall": score(y_true, y_pred)}
    for c in CITIES:
        m = city_arr == c
        if m.any():
            out[c] = score(y_true[m], y_pred[m])
    return out


# ------------------------------------------------------------------------- model
def build_model(window: int, n_features: int, units=(64, 32), dropout=0.2, lr=1e-3):
    from tensorflow import keras
    from tensorflow.keras import layers

    inp = keras.Input(shape=(window, n_features), name="history")
    x = layers.Bidirectional(layers.LSTM(units[0], return_sequences=True), name="bilstm_1")(inp)
    x = layers.Dropout(dropout)(x)
    x = layers.Bidirectional(layers.LSTM(units[1]), name="bilstm_2")(x)
    x = layers.Dropout(dropout)(x)
    x = layers.Dense(32, activation="relu")(x)
    out = layers.Dense(1, name="aqi_next_hour_scaled")(x)
    model = keras.Model(inp, out, name="bilstm_aqi_1h")
    model.compile(optimizer=keras.optimizers.Adam(lr), loss="mse", metrics=["mae"])
    return model


# --------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="models")
    ap.add_argument("--reports-dir", default="reports")
    ap.add_argument("--window", type=int, default=24, help="lookback hours")
    ap.add_argument("--train-frac", type=float, default=0.70)
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--patience", type=int, default=5, help="early-stopping patience (epochs)")
    ap.add_argument("--resume", action="store_true", help="continue from checkpoints/ (resumable training)")
    ap.add_argument("--time-budget", type=float, default=0, help="stop gracefully after N seconds (0 = unlimited)")
    args = ap.parse_args()
    horizon = 1  # one hour ahead

    out_dir, rep_dir = Path(args.out_dir), Path(args.reports_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rep_dir.mkdir(parents=True, exist_ok=True)
    set_seeds(args.seed)

    # 1) load ---------------------------------------------------------------
    raw = {}
    for city in CITIES:
        path = find_city_file(Path(args.data_dir), city)
        raw[city] = pd.read_csv(path)
        print(f"[data] {city:<10} <- {path.name}  ({len(raw[city])} rows)")
    extra_cols = [c for c in OPTIONAL_WEATHER if all(c in df.columns for df in raw.values())]
    print(f"[data] optional weather features used: {extra_cols or 'none (not in CSVs)'}")
    FEATURES, CONT = feature_names(extra_cols)

    # 2) features -----------------------------------------------------------
    feats, imputed = {}, {}
    for city, df in raw.items():
        feats[city], imputed[city] = build_features(df, city, extra_cols)

    # 3) chronological split (calendar cut-offs shared by all cities) ---------
    all_ts = sorted(set().union(*[set(f.index) for f in feats.values()]))
    t_val = all_ts[int(len(all_ts) * args.train_frac)]
    t_test = all_ts[int(len(all_ts) * (args.train_frac + args.val_frac))]
    print(f"[split] train < {t_val} <= val < {t_test} <= test  (last: {all_ts[-1]})")

    # 4) scalers fitted on TRAIN rows only ----------------------------------------
    train_rows = pd.concat([f.loc[f.index < t_val, CONT].dropna() for f in feats.values()])
    scaler = StandardScaler().fit(train_rows.values)
    train_aqi = np.concatenate([f.loc[(f.index < t_val) & ~imputed[c], TARGET].dropna().values
                                for c, f in feats.items()])
    y_mean, y_std = float(train_aqi.mean()), float(train_aqi.std())
    cont_idx = [FEATURES.index(c) for c in CONT]

    # 5) windows ------------------------------------------------------------------
    Xs, ys, ts, cur, cities = [], [], [], [], []
    for city, f in feats.items():
        F = f[FEATURES].values.astype("float64").copy()
        F[:, cont_idx] = (F[:, cont_idx] - scaler.mean_) / scaler.scale_
        ok_target = (~imputed[city].values) & ~np.isnan(f[TARGET].values)
        X, y, t, c_aqi = make_windows(F, f[TARGET].values, ok_target, f.index, args.window, horizon)
        Xs.append(X.astype("float32")); ys.append(y); ts.append(t); cur.append(c_aqi)
        cities.append(np.full(len(y), city))
    X, y, t, cur, city_arr = (np.concatenate(Xs), np.concatenate(ys), np.concatenate(ts),
                              np.concatenate(cur), np.concatenate(cities))
    t = pd.DatetimeIndex(t)
    m_tr, m_va, m_te = t < t_val, (t >= t_val) & (t < t_test), t >= t_test
    y_sc = ((y - y_mean) / y_std).astype("float32")
    print(f"[windows] X={X.shape}  train={m_tr.sum()}  val={m_va.sum()}  test={m_te.sum()}")
    assert t[m_tr].max() < t[m_va].min() <= t[m_va].max() < t[m_te].min(), "splits overlap in time!"

    # 6) train ----------------------------------------------------------------------
    from tensorflow import keras

    ck_dir = out_dir / "checkpoints"
    ck_dir.mkdir(exist_ok=True)
    state_f = ck_dir / "state.json"
    if args.resume and state_f.exists():
        state = json.loads(state_f.read_text())
        model = keras.models.load_model(ck_dir / "last.keras")  # includes optimizer state
        print(f"[resume] continuing after epoch {state['epoch']} (best val_loss {state['best']:.4f})")
    else:
        state = {"epoch": 0, "best": float("inf"), "best_epoch": 0, "wait": 0, "done": False,
                 "history": {"loss": [], "val_loss": []}}
        model = build_model(args.window, len(FEATURES), lr=args.lr)
        model.summary()

    class EpochManager(keras.callbacks.Callback):
        """Early stopping + LR reduction + per-epoch checkpoint (so training can be resumed)."""
        def __init__(self): super().__init__(); self.t0 = time.time()
        def on_epoch_end(self, epoch, logs=None):
            state["epoch"] = epoch + 1
            state["history"]["loss"].append(float(logs["loss"]))
            state["history"]["val_loss"].append(float(logs["val_loss"]))
            if logs["val_loss"] < state["best"] - 1e-4:
                state.update(best=float(logs["val_loss"]), best_epoch=epoch + 1, wait=0)
                self.model.save_weights(ck_dir / "best.weights.h5")
            else:
                state["wait"] += 1
                if state["wait"] % 3 == 0:  # reduce LR on plateau
                    lr = float(keras.backend.get_value(self.model.optimizer.learning_rate))
                    self.model.optimizer.learning_rate.assign(max(lr * 0.5, 1e-5))
                if state["wait"] >= args.patience:
                    state["done"] = True
                    self.model.stop_training = True
            if state["epoch"] >= args.epochs:
                state["done"] = True
            if args.time_budget and time.time() - self.t0 > args.time_budget:
                self.model.stop_training = True
            self.model.save(ck_dir / "last.keras")
            state_f.write_text(json.dumps(state))

    t0 = time.time()
    if not state["done"]:
        model.fit(X[m_tr], y_sc[m_tr], validation_data=(X[m_va], y_sc[m_va]),
                  epochs=args.epochs, initial_epoch=state["epoch"], batch_size=args.batch_size,
                  shuffle=True, callbacks=[EpochManager()], verbose=2)
    if not state["done"]:
        print(f"[paused] epoch {state['epoch']}, best val_loss {state['best']:.4f}. Re-run with --resume.")
        raise SystemExit(3)
    model.load_weights(ck_dir / "best.weights.h5")  # restore best epoch
    hist_hist = state["history"]
    print(f"[train] finished: {state['epoch']} epochs, best epoch = {state['best_epoch']}")

    # 7) evaluate (test split touched only here) ----------------------------------------
    def predict(mask):
        p = model.predict(X[mask], batch_size=1024, verbose=0).ravel() * y_std + y_mean
        return np.clip(p, 0, 500)

    ridge = Ridge(alpha=1.0).fit(X[m_tr][:, -1, :], y[m_tr])  # simple non-sequential baseline
    results = {}
    for name, mask in [("validation", m_va), ("test", m_te)]:
        results[name] = {
            "bilstm": score_by_city(y[mask], predict(mask), city_arr[mask]),
            "baseline_persistence": score_by_city(y[mask], cur[mask], city_arr[mask]),
            "baseline_ridge_last_step": score_by_city(
                y[mask], np.clip(ridge.predict(X[mask][:, -1, :]), 0, 500), city_arr[mask]),
        }
    print("\n=== TEST (overall) ===")
    for k, v in results["test"].items():
        print(f"{k:<26} {v['overall']}")
    print("\n=== TEST (per city, Bi-LSTM) ===")
    for c in CITIES:
        print(f"{c:<10} {results['test']['bilstm'][c]}")

    # 8) save ---------------------------------------------------------------------------
    model.save(out_dir / MODEL_FILE)
    joblib.dump({
        "feature_scaler": scaler, "continuous_cols": CONT, "features": FEATURES,
        "target_mean": y_mean, "target_std": y_std,
    }, out_dir / SCALER_FILE)

    import sklearn, tensorflow as tf
    meta = {
        "task": "1-hour-ahead AQI forecast, shared Bi-LSTM for all cities",
        "window_hours": args.window, "horizon_hours": horizon,
        "min_history_hours": args.window + MAX_ROLL - 1,
        "cities": CITIES, "pollutants": POLLUTANTS, "extra_cols": extra_cols,
        "features": FEATURES, "continuous_cols": CONT,
        "split": {"train_end_exclusive": str(t_val), "val_end_exclusive": str(t_test),
                  "n_train": int(m_tr.sum()), "n_val": int(m_va.sum()), "n_test": int(m_te.sum())},
        "metrics": results,
        "best_epoch": state["best_epoch"],
        "versions": {"tensorflow": tf.__version__, "keras": keras.__version__,
                     "scikit_learn": sklearn.__version__, "numpy": np.__version__, "pandas": pd.__version__},
        "seed": args.seed,
    }
    (out_dir / META_FILE).write_text(json.dumps(meta, indent=2))
    (rep_dir / "metrics.json").write_text(json.dumps(results, indent=2))

    pred_df = pd.DataFrame({"city": city_arr[m_te], "timestamp": t[m_te], "actual_aqi": y[m_te],
                            "pred_bilstm": predict(m_te), "pred_persistence": cur[m_te]})
    pred_df.to_csv(rep_dir / "test_predictions.csv", index=False)

    # plots
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(13, 4))
    ax[0].plot(hist_hist["loss"], label="train"); ax[0].plot(hist_hist["val_loss"], label="val")
    ax[0].set(title="Training curve (MSE, scaled AQI)", xlabel="epoch"); ax[0].legend()
    d = pred_df[pred_df.city == "Delhi"].iloc[:24 * 14]
    ax[1].plot(d.timestamp, d.actual_aqi, label="actual", lw=1.2)
    ax[1].plot(d.timestamp, d.pred_bilstm, label="Bi-LSTM (t+1h)", lw=1.2)
    ax[1].set(title="Delhi - first 14 test days"); ax[1].legend(); fig.autofmt_xdate()
    fig.tight_layout(); fig.savefig(rep_dir / "training_and_test_plot.png", dpi=130)
    print(f"\n[saved] {out_dir / MODEL_FILE}, {out_dir / SCALER_FILE}, {out_dir / META_FILE}, reports -> {rep_dir}")


if __name__ == "__main__":
    main()
