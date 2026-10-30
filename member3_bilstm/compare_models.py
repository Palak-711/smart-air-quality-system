"""
compare_models.py
=================
Fair comparison for the report section "Comparison with the Existing Work".
Every model sees the SAME windows, the SAME chronological split and the SAME scaler as the Bi-LSTM
(data preparation is identical to train_bilstm.py).

Models
  Persistence            : AQI(t+1) = AQI(t)
  Ridge (linear)         : last-hour features only
  Gradient Boosting      : HistGradientBoostingRegressor, last-hour features only
  LSTM (unidirectional)  : same layout as the Bi-LSTM but one direction
  Bi-LSTM (ours)         : the saved model in models/

    python compare_models.py --data-dir data
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
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

from aqi_common import CITIES, TARGET, build_features, feature_names, OPTIONAL_WEATHER
from train_bilstm import find_city_file, make_windows, score_by_city, set_seeds


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--model-dir", default="models")
    ap.add_argument("--out-dir", default="reports")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--time-budget", type=float, default=230, help="max seconds for LSTM training")
    a = ap.parse_args()
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers

    set_seeds(a.seed)
    model_dir, out = Path(a.model_dir), Path(a.out_dir)
    meta = json.loads((model_dir / "bilstm_aqi_metadata.json").read_text())
    bundle = joblib.load(model_dir / "bilstm_aqi_scaler.joblib")
    window, extra = meta["window_hours"], meta["extra_cols"]
    FEATURES, CONT = feature_names(extra)
    t_val, t_test = pd.Timestamp(meta["split"]["train_end_exclusive"]), pd.Timestamp(meta["split"]["val_end_exclusive"])
    scaler, y_mean, y_std = bundle["feature_scaler"], bundle["target_mean"], bundle["target_std"]
    cont_idx = [FEATURES.index(c) for c in CONT]

    Xs, ys, ts, cur, cities = [], [], [], [], []
    for city in CITIES:
        df = pd.read_csv(find_city_file(Path(a.data_dir), city))
        f, imputed = build_features(df, city, extra)
        F = f[FEATURES].values.astype("float64").copy()
        F[:, cont_idx] = (F[:, cont_idx] - scaler.mean_) / scaler.scale_
        ok_t = (~imputed.values) & ~np.isnan(f[TARGET].values)
        X, y, t, c = make_windows(F, f[TARGET].values, ok_t, f.index, window, 1)
        Xs.append(X.astype("float32")); ys.append(y); ts.append(t); cur.append(c); cities.append(np.full(len(y), city))
    X, y, cur, city_arr = np.concatenate(Xs), np.concatenate(ys), np.concatenate(cur), np.concatenate(cities)
    t = pd.DatetimeIndex(np.concatenate(ts))
    m_tr, m_va, m_te = t < t_val, (t >= t_val) & (t < t_test), t >= t_test
    y_sc = ((y - y_mean) / y_std).astype("float32")
    print(f"windows: train {m_tr.sum()}  val {m_va.sum()}  test {m_te.sum()}")

    preds = {"Persistence": cur[m_te]}
    ridge = Ridge(alpha=1.0).fit(X[m_tr][:, -1, :], y[m_tr])
    preds["Ridge (linear)"] = ridge.predict(X[m_te][:, -1, :])
    gb = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, early_stopping=False, random_state=a.seed)
    gb.fit(X[m_tr][:, -1, :], y[m_tr])
    preds["Gradient Boosting"] = gb.predict(X[m_te][:, -1, :])
    print("classical models done")

    # unidirectional LSTM, same layout / settings as the Bi-LSTM
    inp = keras.Input(shape=(window, len(FEATURES)))
    x = layers.LSTM(64, return_sequences=True)(inp); x = layers.Dropout(0.2)(x)
    x = layers.LSTM(32)(x); x = layers.Dropout(0.2)(x)
    x = layers.Dense(32, activation="relu")(x); out_l = layers.Dense(1)(x)
    lstm = keras.Model(inp, out_l); lstm.compile(optimizer=keras.optimizers.Adam(1e-3), loss="mse")
    t0 = time.time()

    class Budget(keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            if time.time() - t0 > a.time_budget:
                self.model.stop_training = True
    h = lstm.fit(X[m_tr], y_sc[m_tr], validation_data=(X[m_va], y_sc[m_va]), epochs=40, batch_size=256, verbose=2,
                 callbacks=[keras.callbacks.EarlyStopping(patience=5, restore_best_weights=True),
                            keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=3, min_lr=1e-5), Budget()])
    print(f"LSTM epochs run: {len(h.history['loss'])}, best val_loss {min(h.history['val_loss']):.4f}")
    preds["LSTM"] = lstm.predict(X[m_te], batch_size=1024, verbose=0).ravel() * y_std + y_mean

    bilstm = keras.models.load_model(model_dir / "bilstm_aqi_1h.keras", compile=False)
    preds["Bi-LSTM (ours)"] = bilstm.predict(X[m_te], batch_size=1024, verbose=0).ravel() * y_std + y_mean

    res = {k: score_by_city(y[m_te], np.clip(v, 0, 500), city_arr[m_te]) for k, v in preds.items()}
    (out / "comparison_metrics.json").write_text(json.dumps(res, indent=2))
    for k, v in res.items():
        print(f"{k:<20} {v['overall']}")


if __name__ == "__main__":
    main()
