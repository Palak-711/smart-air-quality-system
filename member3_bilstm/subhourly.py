"""
subhourly.py  --  SIMULATED 15-minute data + features for the 15/30-minute models
===============================================================================
The real CSVs are HOURLY. To demonstrate 15- and 30-minute forecasting we SIMULATE a 15-minute series:

  * every :00 value is the REAL hourly reading (kept exactly),
  * the three values in between (:15, :30, :45) are a straight line between the two real hourly readings
    plus a "Brownian-bridge" random wiggle that starts and ends at zero, so the real readings are preserved.
  * wiggles are partly shared across pollutants/AQI (SIM_RHO) so they stay correlated; size is a fraction
    (SIM_KAPPA) of the typical hour-to-hour change of each column.

IMPORTANT: results obtained on this data measure how well a model learns THIS simulation, not real 15/30-minute
air-quality dynamics. Always call it "simulated" in the report.

Leakage note: simulated :15/:30/:45 points of an hour already point toward the NEXT real hour. Therefore the
sub-hourly models only issue forecasts from the top of the hour (origin minute = 0), where the history contains
only intervals that are completely in the past.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from aqi_common import CITIES, POLLUTANTS, TARGET, normalize_city, regularize_hourly

STEP_MIN = 15
SIM_KAPPA = 0.35
SIM_RHO = 0.6
ROLL_STEPS = (4, 12, 24, 96)  # 1h, 3h, 6h, 24h in 15-minute steps
MAX_ROLL_STEPS = max(ROLL_STEPS)
HORIZON_STEPS = (1, 2)        # 15 and 30 minutes ahead
MAX_FFILL_STEPS = 12
VALUE_COLS = POLLUTANTS + [TARGET]


def simulate_15min(df_hourly: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Hourly dataframe (timestamp + VALUE_COLS) -> simulated 15-minute dataframe.

    Columns: VALUE_COLS, `imputed` (row touches a filled/missing hour), `is_real_hourly` (minute == 0).
    """
    d, imputed = regularize_hourly(df_hourly, VALUE_COLS)
    n = len(d)
    nint = n - 1
    rng = np.random.default_rng(seed)
    idx = pd.date_range(d.index[0], periods=nint * 4 + 1, freq=f"{STEP_MIN}min")
    shared = rng.standard_normal((nint, 4))
    k = np.arange(1, 4) / 4.0
    out = {}
    for c in VALUE_COLS:
        v = d[c].values.astype(float)
        sigma = SIM_KAPPA * np.nanstd(np.diff(v))
        own = rng.standard_normal((nint, 4))
        steps = (np.sqrt(SIM_RHO) * shared + np.sqrt(1 - SIM_RHO) * own) * sigma
        W = np.cumsum(steps, axis=1)
        bridge = W[:, :3] - k[None, :] * W[:, 3:4]          # starts and ends at 0
        interior = v[:-1, None] + k[None, :] * (v[1:] - v[:-1])[:, None] + bridge
        arr = np.full(len(idx), np.nan)
        arr[::4] = v
        for j in range(3):
            arr[4 * np.arange(nint) + (j + 1)] = interior[:, j]
        arr = np.clip(arr, 0.0, 500.0 if c == TARGET else None)
        out[c] = arr
    res = pd.DataFrame(out, index=idx)
    imp_h = imputed.values
    imp = np.zeros(len(idx), dtype=bool)
    imp[::4] = imp_h
    for j in range(1, 4):
        imp[j::4][:nint] = imp_h[:-1] | imp_h[1:]
    res["imputed"] = imp
    res["is_real_hourly"] = (idx.minute.values == 0)
    res.index.name = "timestamp"
    return res


def regularize_15min(df: pd.DataFrame) -> pd.DataFrame:
    """Raw 15-minute history -> strict 15-minute grid (causal forward-fill, at most 3 hours)."""
    d = df.copy()
    d["timestamp"] = pd.to_datetime(d["timestamp"])
    d = d.sort_values("timestamp").drop_duplicates("timestamp", keep="last").set_index("timestamp")
    d = d.reindex(pd.date_range(d.index.min(), d.index.max(), freq=f"{STEP_MIN}min"))
    d[VALUE_COLS] = d[VALUE_COLS].astype(float).ffill(limit=MAX_FFILL_STEPS)
    d.index.name = "timestamp"
    return d


def feature_names_15min() -> tuple[list[str], list[str]]:
    rolled = [f"aqi_roll{w}" for w in ROLL_STEPS] + [f"pm25_roll{w}" for w in ROLL_STEPS]
    continuous = VALUE_COLS + rolled + ["aqi_diff1", "aqi_diff4"]
    cyc = ["tod_sin", "tod_cos", "dow_sin", "dow_cos", "doy_sin", "doy_cos", "is_weekend"]
    return continuous + cyc + [f"city_{c}" for c in CITIES], continuous


def build_features_15min(df15: pd.DataFrame, city: str) -> pd.DataFrame:
    """Causal features on a regular 15-minute frame (index = timestamp)."""
    city = normalize_city(city)
    f = df15[VALUE_COLS].astype(float).copy()
    for w in ROLL_STEPS:
        f[f"aqi_roll{w}"] = f[TARGET].rolling(w, min_periods=w).mean()
        f[f"pm25_roll{w}"] = f["pm25"].rolling(w, min_periods=w).mean()
    f["aqi_diff1"] = f[TARGET].diff(1)
    f["aqi_diff4"] = f[TARGET].diff(4)
    idx = f.index
    tod = (idx.hour.values * 60 + idx.minute.values) / 1440.0
    dow, doy = idx.dayofweek.values, idx.dayofyear.values
    f["tod_sin"], f["tod_cos"] = np.sin(2 * np.pi * tod), np.cos(2 * np.pi * tod)
    f["dow_sin"], f["dow_cos"] = np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7)
    f["doy_sin"], f["doy_cos"] = np.sin(2 * np.pi * doy / 366), np.cos(2 * np.pi * doy / 366)
    f["is_weekend"] = (dow >= 5).astype(float)
    for c in CITIES:
        f[f"city_{c}"] = float(c == city)
    return f[feature_names_15min()[0]]
