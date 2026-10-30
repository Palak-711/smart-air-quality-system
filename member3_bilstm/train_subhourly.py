"""
train_subhourly.py  --  Bi-LSTM that forecasts AQI 15 and 30 minutes ahead (SIMULATED 15-minute data)
=====================================================================================================
One Bi-LSTM with two outputs (t+15 min, t+30 min). Same chronological split dates as the hourly model.
Forecasts are issued from the top of each hour (see subhourly.py for why).

Compared on the SAME test points:
  persistence | Ridge | interpolation using the hourly Bi-LSTM (the earlier "option 1") |
  oracle interpolation (cheats: uses the next real hour; shows the best possible on simulated data) | Bi-LSTM

    python train_subhourly.py --data-dir data --time-budget 200            # run repeatedly with --resume
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from aqi_common import CITIES, TARGET, build_features, feature_names
from subhourly import (HORIZON_STEPS, MAX_ROLL_STEPS, STEP_MIN, build_features_15min, feature_names_15min, simulate_15min)
from train_bilstm import find_city_file, make_windows, score, score_by_city, set_seeds

MODEL_FILE, SCALER_FILE, META_FILE = "bilstm_aqi_15_30min.keras", "bilstm_aqi_15_30min_scaler.joblib", "bilstm_aqi_15_30min_metadata.json"


def make_windows_multi(F, y, ok_target, times, window, origin_mask):
    """Windows ending at hour-aligned origins; targets at +15 and +30 min; also returns persistence and the next real hour."""
    n = len(F)
    ok_row = ~np.isnan(F).any(axis=1)
    ends = np.arange(window - 1, n - 4)
    ends = ends[origin_mask[ends]]
    starts = ends - window + 1
    bad = np.concatenate([[0], np.cumsum(~ok_row)])
    keep = (bad[ends + 1] - bad[starts]) == 0
    for h in HORIZON_STEPS:
        keep &= ok_target[ends + h]
    keep &= ok_target[ends + 4]
    ends = ends[keep]
    idx = ends[:, None] + np.arange(-window + 1, 1)[None, :]
    Y = np.stack([y[ends + h] for h in HORIZON_STEPS], axis=1)
    return F[idx], Y, times[ends], times[ends + max(HORIZON_STEPS)], y[ends], y[ends + 4]


def build_model(window, n_feat, n_out, lr=1e-3):
    from tensorflow import keras
    from tensorflow.keras import layers

    inp = keras.Input(shape=(window, n_feat), name="history15")
    x = layers.Bidirectional(layers.LSTM(64, return_sequences=True), name="bilstm_1")(inp)
    x = layers.Dropout(0.2)(x)
    x = layers.Bidirectional(layers.LSTM(32), name="bilstm_2")(x)
    x = layers.Dropout(0.2)(x)
    x = layers.Dense(32, activation="relu")(x)
    out = layers.Dense(n_out, name="aqi_15_30_scaled")(x)
    m = keras.Model(inp, out, name="bilstm_aqi_15_30min")
    m.compile(optimizer=keras.optimizers.Adam(lr), loss="mse")
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="models")
    ap.add_argument("--reports-dir", default="reports")
    ap.add_argument("--window", type=int, default=24, help="lookback in 15-minute steps (24 = 6 hours)")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--patience", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--time-budget", type=float, default=0)
    a = ap.parse_args()
    out_dir, rep = Path(a.out_dir), Path(a.reports_dir)
    sim_dir = rep / "simulated_15min"
    sim_dir.mkdir(parents=True, exist_ok=True)
    set_seeds(a.seed)

    hmeta = json.loads((out_dir / "bilstm_aqi_metadata.json").read_text())
    t_val, t_test = pd.Timestamp(hmeta["split"]["train_end_exclusive"]), pd.Timestamp(hmeta["split"]["val_end_exclusive"])
    FEATS, CONT = feature_names_15min()
    cont_idx = [FEATS.index(c) for c in CONT]

    # ---------------- simulate + features (per city) ----------------
    frames, feats = {}, {}
    for i, city in enumerate(CITIES):
        raw = pd.read_csv(find_city_file(Path(a.data_dir), city))
        sim = simulate_15min(raw, seed=a.seed + i)
        sim.to_csv(sim_dir / f"{city.lower()}_15min_SIMULATED.csv")
        frames[city], feats[city] = sim, build_features_15min(sim, city)

    # scaler: training rows only (stop 1 h before val start: interior points look ahead to the next hour)
    train_rows = pd.concat([f.loc[f.index < t_val - pd.Timedelta(hours=1), CONT].dropna() for f in feats.values()])
    scaler = StandardScaler().fit(train_rows.values)
    tr_aqi = np.concatenate([frames[c].loc[(frames[c].index < t_val - pd.Timedelta(hours=1)) & ~frames[c].imputed, TARGET].values for c in CITIES])
    y_mean, y_std = float(tr_aqi.mean()), float(tr_aqi.std())

    Xs, Ys, T0, T30, CUR, NXT, CITY = [], [], [], [], [], [], []
    for city in CITIES:
        f, sim = feats[city], frames[city]
        F = f.values.astype("float64").copy()
        F[:, cont_idx] = (F[:, cont_idx] - scaler.mean_) / scaler.scale_
        ok_t = (~sim.imputed.values) & ~np.isnan(sim[TARGET].values)
        X, Y, t0, t30, cur, nxt = make_windows_multi(F, sim[TARGET].values, ok_t, f.index, a.window, sim.is_real_hourly.values)
        Xs.append(X.astype("float32")); Ys.append(Y); T0.append(t0); T30.append(t30); CUR.append(cur); NXT.append(nxt)
        CITY.append(np.full(len(cur), city))
    X, Y, cur, nxt, city_arr = map(np.concatenate, (Xs, Ys, CUR, NXT, CITY))
    t0, t30 = pd.DatetimeIndex(np.concatenate(T0)), pd.DatetimeIndex(np.concatenate(T30))
    m_tr, m_va, m_te = t30 < t_val, (t30 >= t_val) & (t30 < t_test), t30 >= t_test
    assert t30[m_tr].max() < t30[m_va].min() <= t30[m_va].max() < t30[m_te].min()
    Y_sc = ((Y - y_mean) / y_std).astype("float32")
    print(f"[windows] X={X.shape}  train={m_tr.sum()} val={m_va.sum()} test={m_te.sum()}", flush=True)

    # ---------------- train (resumable) ----------------
    from tensorflow import keras

    ck = out_dir / "checkpoints_15_30"; ck.mkdir(exist_ok=True)
    state_f = ck / "state.json"
    if a.resume and state_f.exists():
        state = json.loads(state_f.read_text()); model = keras.models.load_model(ck / "last.keras")
        print(f"[resume] after epoch {state['epoch']} (best {state['best']:.4f})", flush=True)
    else:
        state = {"epoch": 0, "best": float("inf"), "best_epoch": 0, "wait": 0, "done": False, "history": {"loss": [], "val_loss": []}}
        model = build_model(a.window, len(FEATS), len(HORIZON_STEPS))

    class EM(keras.callbacks.Callback):
        def __init__(self): super().__init__(); self.t0 = time.time()
        def on_epoch_end(self, epoch, logs=None):
            state["epoch"] = epoch + 1
            state["history"]["loss"].append(float(logs["loss"])); state["history"]["val_loss"].append(float(logs["val_loss"]))
            if logs["val_loss"] < state["best"] - 1e-4:
                state.update(best=float(logs["val_loss"]), best_epoch=epoch + 1, wait=0); self.model.save_weights(ck / "best.weights.h5")
            else:
                state["wait"] += 1
                if state["wait"] % 3 == 0:
                    lr = float(keras.backend.get_value(self.model.optimizer.learning_rate))
                    self.model.optimizer.learning_rate.assign(max(lr * 0.5, 1e-5))
                if state["wait"] >= a.patience: state["done"] = True; self.model.stop_training = True
            if state["epoch"] >= a.epochs: state["done"] = True
            if a.time_budget and time.time() - self.t0 > a.time_budget: self.model.stop_training = True
            self.model.save(ck / "last.keras"); state_f.write_text(json.dumps(state))

    if not state["done"]:
        model.fit(X[m_tr], Y_sc[m_tr], validation_data=(X[m_va], Y_sc[m_va]), epochs=a.epochs, initial_epoch=state["epoch"],
                  batch_size=a.batch_size, shuffle=True, callbacks=[EM()], verbose=2)
    if not state["done"]:
        print(f"[paused] epoch {state['epoch']}, best val_loss {state['best']:.4f}. Re-run with --resume.", flush=True)
        raise SystemExit(3)
    model.load_weights(ck / "best.weights.h5")
    print(f"[train] finished: {state['epoch']} epochs, best epoch {state['best_epoch']}", flush=True)

    # ---------------- hourly Bi-LSTM forecast at the same origins (for the interpolation baseline) ----------------
    hb = joblib.load(out_dir / "bilstm_aqi_scaler.joblib")
    hmodel = keras.models.load_model(out_dir / "bilstm_aqi_1h.keras", compile=False)
    HF, HC = feature_names(hmeta["extra_cols"]); hidx = [HF.index(c) for c in HC]
    rows = []
    for city in CITIES:
        df = pd.read_csv(find_city_file(Path(a.data_dir), city))
        f, imp = build_features(df, city, hmeta["extra_cols"])
        Fh = f[HF].values.astype("float64").copy(); Fh[:, hidx] = (Fh[:, hidx] - hb["feature_scaler"].mean_) / hb["feature_scaler"].scale_
        Xh, _, th, _ = make_windows(Fh, f[TARGET].values, np.ones(len(f), bool), f.index, hmeta["window_hours"], 1)
        p = hmodel.predict(Xh.astype("float32"), batch_size=1024, verbose=0).ravel() * hb["target_std"] + hb["target_mean"]
        rows.append(pd.DataFrame({"city": city, "origin": pd.DatetimeIndex(th) - pd.Timedelta(hours=1), "p60": np.clip(p, 0, 500)}))
    hp = pd.concat(rows)
    key = pd.DataFrame({"city": city_arr, "origin": t0, "i": np.arange(len(t0))}).merge(hp, on=["city", "origin"], how="left")
    p60 = key.sort_values("i").p60.values

    # ---------------- evaluate on the test split ----------------
    pred = np.clip(model.predict(X[m_te], batch_size=1024, verbose=0) * y_std + y_mean, 0, 500)
    have = ~np.isnan(p60[m_te])  # origins where the hourly model also has a forecast: compare everything on these
    res = {"n_test_total": int(m_te.sum()), "n_test_compared": int(have.sum()), "horizons": {}}
    ridge = {h: Ridge(alpha=1.0).fit(X[m_tr][:, -1, :], Y[m_tr][:, j]) for j, h in enumerate(HORIZON_STEPS)}
    pred_rows = {"city": city_arr[m_te][have], "origin": t0[m_te][have]}
    for j, h in enumerate(HORIZON_STEPS):
        minutes = h * STEP_MIN; w = minutes / 60.0
        y_te, c_te, n_te, p_te, ct = Y[m_te][:, j][have], cur[m_te][have], nxt[m_te][have], p60[m_te][have], city_arr[m_te][have]
        res["horizons"][f"{minutes}min"] = {
            "Persistence": score_by_city(y_te, c_te, ct),
            "Ridge": score_by_city(y_te, np.clip(ridge[h].predict(X[m_te][have][:, -1, :]), 0, 500), ct),
            "Interpolation (hourly Bi-LSTM)": score_by_city(y_te, np.clip(c_te + w * (p_te - c_te), 0, 500), ct),
            "Bi-LSTM 15/30 (ours)": score_by_city(y_te, pred[have][:, j], ct),
            "Oracle interpolation (uses next real hour)": score_by_city(y_te, c_te + w * (n_te - c_te), ct),
        }
        pred_rows[f"actual_{minutes}min_simulated"] = y_te; pred_rows[f"pred_{minutes}min"] = pred[have][:, j]
        print(f"\n=== {minutes} min (SIMULATED target), overall ===", flush=True)
        for k, v in res["horizons"][f"{minutes}min"].items(): print(f"{k:<46} {v['overall']}", flush=True)

    out_dir.mkdir(exist_ok=True)
    model.save(out_dir / MODEL_FILE)
    joblib.dump({"feature_scaler": scaler, "continuous_cols": CONT, "features": FEATS, "target_mean": y_mean, "target_std": y_std}, out_dir / SCALER_FILE)
    import sklearn, tensorflow as tf
    meta = {"task": "15- and 30-minute-ahead AQI forecast trained on SIMULATED 15-minute data (derived from real hourly data)",
            "SIMULATED_DATA": True, "step_minutes": STEP_MIN, "window_steps": a.window, "horizons_minutes": [h * STEP_MIN for h in HORIZON_STEPS],
            "min_history_steps": a.window + MAX_ROLL_STEPS - 1, "origin": "top of the hour (minute 00)", "features": FEATS,
            "split": hmeta["split"], "best_epoch": state["best_epoch"], "metrics": res,
            "versions": {"tensorflow": tf.__version__, "keras": keras.__version__, "scikit_learn": sklearn.__version__}}
    (out_dir / META_FILE).write_text(json.dumps(meta, indent=2))
    (rep / "subhourly_metrics.json").write_text(json.dumps(res, indent=2))
    pd.DataFrame(pred_rows).to_csv(rep / "subhourly_test_predictions.csv", index=False)
    print("[saved]", out_dir / MODEL_FILE, flush=True)


if __name__ == "__main__":
    main()
