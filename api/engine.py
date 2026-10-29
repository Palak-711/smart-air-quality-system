"""
api/engine.py  --  the "brain" behind the FastAPI endpoints (Member 5)
=====================================================================
One tick of the system:

    sensor reading  ->  (DCAE calibration)  ->  append to the city's hourly history buffer
                    ->  Bi-LSTM forecast for the NEXT hour
                    ->  rule engine (rules.py)  ->  actuation state + audit log
                    ->  dashboard state / MQTT command back to the ESP32

SIMULATION CLOCK (important, say this in the viva):
    The model was trained on HOURLY data and predicts 1 hour ahead. The Wokwi node publishes a
    reading every few seconds, so ONE MQTT MESSAGE = ONE SIMULATED HOUR. The history buffer is
    warmed up with the last 72 real hours from the dataset (a node needs 47 h of history before
    it can forecast), and live node readings continue the series from there.

OUTDOOR REFERENCE:
    The dataset itself is replayed as the "outdoor" AQI feed, one hour per tick, so the rule
    engine can make context-aware ventilation decisions (indoor vs outdoor).
"""
from __future__ import annotations

import os
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable, Deque, Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:          # so `import aqi_common` / `import inference` work from api/
    sys.path.insert(0, str(ROOT))

from aqi_common import CITIES, aqi_category, normalize_city      # noqa: E402
from api import rules                                             # noqa: E402

POLLUTANTS = ["pm25", "pm10", "no2", "o3", "co", "so2"]
HISTORY_LEN = 96           # rows kept per city (>= 47 needed by the model)
SEED_ROWS = 72
CHART_POINTS = 24

# --- PM2.5 -> AQI mapping, measured on the project dataset (binned means of aqi vs pm25) ----------
# The dataset's AQI is a piecewise-linear function of PM2.5 (corr = 0.96), so we reuse that mapping
# for sensor readings. Above 170 ug/m3 the dataset has no samples: extrapolated CPCB-style.
_PM = [0, 2.7, 7.6, 12.6, 17.6, 22.5, 27.5, 32.5, 37.5, 42.5, 47.5, 52.5, 57.5, 62.5, 67.5,
       74.8, 84.8, 94.6, 107.5, 126.4, 146.0, 170.0, 250.0, 350.0, 500.0]
_AQI = [0, 11.3, 31.7, 51.1, 62.7, 73.1, 83.5, 94.0, 111.4, 136.2, 161.0, 185.8, 203.1, 208.4,
        213.6, 221.2, 231.7, 241.9, 255.3, 275.0, 295.6, 305.0, 400.0, 450.0, 500.0]


def pm25_to_aqi(pm25: float) -> float:
    return float(np.interp(pm25, _PM, _AQI))


def aqi_to_pm25(aqi: float) -> float:
    return float(np.interp(aqi, _AQI, _PM))


ADVISORY = {
    "Good": "Air quality is good. Enjoy normal activities.",
    "Satisfactory": "Acceptable air. Unusually sensitive people should take minor care.",
    "Moderate": "Moderate air quality. Sensitive people should limit prolonged outdoor exertion.",
    "Poor": "Poor air quality. Breathing discomfort on prolonged exposure. Keep windows closed, wear a mask outdoors.",
    "Very Poor": "VERY POOR air. Respiratory illness on prolonged exposure. Stay indoors, wear an N95 mask outside.",
    "Severe": "SEVERE ALERT. Health emergency conditions. Stay indoors with the purifier on HIGH.",
}


# =============================================================================================
#  Data loading
# =============================================================================================
def find_city_csv(data_dir: Path, city: str) -> Path:
    """Same preference order as train_bilstm.find_city_file: calibrated > cleaned > raw."""
    prefixes = [city.lower()] + (["gurgaon"] if city == "Gurugram" else [])
    cands = [p for p in data_dir.rglob("*.csv") if any(p.name.lower().startswith(x) for x in prefixes)]
    if not cands:
        raise FileNotFoundError(f"No CSV for {city} under {data_dir}")

    def rank(p: Path):
        n = p.name.lower()
        return (0 if "calibrated" in n else 1 if "cleaned" in n else 2, str(p))

    return sorted(cands, key=rank)[0]


def load_city_series(data_dir: Path, city: str) -> pd.DataFrame:
    """Hourly, gap-free, artefact-free series for one city (index = timestamp)."""
    df = pd.read_csv(find_city_csv(data_dir, city), parse_dates=["timestamp"])
    df = df.sort_values("timestamp").drop_duplicates("timestamp").set_index("timestamp")
    df = df[POLLUTANTS + ["aqi"]].astype(float)
    # The dataset contains rows where pm25 == 0 and aqi == 0 (clipped sensor drop-outs, ~2.5 %).
    # They are not real air quality, so treat them as missing and carry the last value forward.
    df.loc[df["pm25"] <= 0, POLLUTANTS + ["aqi"]] = np.nan
    df = df.reindex(pd.date_range(df.index.min(), df.index.max(), freq="h"))
    return df.ffill(limit=3).dropna()


# =============================================================================================
#  Optional components (degrade gracefully when TensorFlow / model files are missing)
# =============================================================================================
class Calibrator:
    """DCAE sensor calibration, loaded ONCE (the original sensor_inference.py reloaded it per call)."""
    FEATURES = ["pm25", "pm10", "co", "no2", "so2"]

    def __init__(self, model_dir: Path):
        self.model = None
        self.scaler = None
        self.error: Optional[str] = None
        try:
            import joblib
            from tensorflow import keras
            self.model = keras.models.load_model(model_dir / "best_dcae_sensor_model.h5", compile=False)
            self.scaler = joblib.load(model_dir / "scaler.pkl")
        except Exception as e:                      # noqa: BLE001
            self.error = f"{type(e).__name__}: {e}"

    @property
    def active(self) -> bool:
        return self.model is not None

    def apply(self, row: Dict[str, float]) -> Dict[str, float]:
        if not self.active:
            return dict(row)
        x = np.array([[row[f] for f in self.FEATURES]], dtype="float64")
        z = self.scaler.transform(x)[:, None, :].astype("float32")
        rec = np.asarray(self.model(z, training=False)).squeeze(axis=1)
        out = self.scaler.inverse_transform(rec)[0]
        res = dict(row)
        res.update({f: max(0.0, float(v)) for f, v in zip(self.FEATURES, out)})
        return res


def _fallback_forecast(aqis: List[float]) -> float:
    """Used ONLY if the Bi-LSTM cannot be loaded: persistence + damped short-term trend."""
    last = aqis[-1]
    trend = last - float(np.mean(aqis[-4:-1])) if len(aqis) >= 4 else 0.0
    return float(np.clip(last + 0.5 * trend, 0, 500))


# =============================================================================================
#  Per-city runtime state
# =============================================================================================
class CityRuntime:
    def __init__(self, city: str, series: pd.DataFrame, start: pd.Timestamp):
        self.city = city
        self.series = series
        pos = int(series.index.searchsorted(start))
        pos = max(SEED_ROWS, min(pos, len(series) - 1))
        self.cursor = pos                           # next outdoor row to be "observed"
        seed = series.iloc[pos - SEED_ROWS:pos]
        self.history: Deque[dict] = deque(maxlen=HISTORY_LEN)
        for ts, r in seed.iterrows():
            self.history.append({"timestamp": ts, **{k: float(r[k]) for k in POLLUTANTS + ["aqi"]}})
        self.sim_time: pd.Timestamp = seed.index[-1]
        self.actuation = rules.ActuationState()
        self.chart: Deque[dict] = deque(maxlen=CHART_POINTS)
        self.last_forecast: Optional[float] = None
        self.last_state: Optional[dict] = None
        self.node: Dict[str, object] = {}
        self.outdoor_aqi = float(seed["aqi"].iloc[-1])
        self.ticks = 0
        # pre-fill the chart with the last real hours so the graph is not empty on first load
        for r in list(self.history)[-CHART_POINTS:]:
            self.chart.append({"t": r["timestamp"].strftime("%d %b %H:%M"), "actual": round(r["aqi"], 1),
                               "predicted": None})

    def next_outdoor(self) -> dict:
        r = self.series.iloc[self.cursor % len(self.series)]
        self.cursor += 1
        return {k: float(r[k]) for k in POLLUTANTS + ["aqi"]}


# =============================================================================================
#  Engine
# =============================================================================================
class Engine:
    def __init__(self, model_dir: Optional[Path] = None, data_dir: Optional[Path] = None,
                 start: Optional[str] = None, use_model: bool = True, use_dcae: bool = True):
        self.model_dir = Path(model_dir or os.environ.get("AQI_MODEL_DIR") or ROOT / "models")
        self.data_dir = Path(data_dir or os.environ.get("AQI_DATA_DIR") or ROOT / "data")
        start_ts = pd.Timestamp(start or os.environ.get("AQI_SIM_START") or "2023-11-01 00:00:00")
        self.lock = threading.RLock()
        self.log: Deque[dict] = deque(maxlen=500)
        self.listeners: List[Callable[[str, dict], None]] = []

        self.forecaster = None
        self.model_error: Optional[str] = None
        if use_model:
            try:
                from inference import get_forecaster
                self.forecaster = get_forecaster(self.model_dir)
            except Exception as e:                  # noqa: BLE001
                self.model_error = f"{type(e).__name__}: {e}"
        else:
            self.model_error = "disabled"
        self.calibrator = Calibrator(self.model_dir) if use_dcae else None

        self.cities: Dict[str, CityRuntime] = {}
        for c in CITIES:
            self.cities[c] = CityRuntime(c, load_city_series(self.data_dir, c), start_ts)
        self._log("SYSTEM", None, f"Engine ready. Forecaster={'Bi-LSTM' if self.forecaster else 'FALLBACK'}, "
                               f"DCAE={'on' if self.calibrator and self.calibrator.active else 'off'}")

    # ------------------------------------------------------------------ helpers
    def _log(self, kind: str, city: Optional[str], msg: str, **extra) -> None:
        self.log.appendleft({"ts": datetime.now().strftime("%H:%M:%S"), "kind": kind, "city": city,
                             "message": msg, **extra})

    def add_listener(self, fn: Callable[[str, dict], None]) -> None:
        self.listeners.append(fn)

    def _forecast(self, rt: CityRuntime) -> tuple[float, str]:
        if self.forecaster is not None:
            try:
                df = pd.DataFrame(list(rt.history))
                out = self.forecaster.predict(df, rt.city)
                return float(out["predicted_aqi"]), "bilstm"
            except Exception as e:                  # noqa: BLE001
                self._log("WARN", rt.city, f"Bi-LSTM failed, using fallback: {e}")
        return _fallback_forecast([r["aqi"] for r in rt.history]), "fallback-trend"

    # ------------------------------------------------------------------ main entry points
    def ingest(self, reading: dict, source: str = "esp32") -> dict:
        """reading: city, pm25 (ug/m3) [or aqi], optional pm10, temperature, humidity, rssi, node_id."""
        city = normalize_city(reading.get("city", "Delhi"))
        with self.lock:
            rt = self.cities[city]
            outdoor = rt.next_outdoor()
            rt.outdoor_aqi = outdoor["aqi"]
            last = rt.history[-1]

            if reading.get("aqi") is not None and reading.get("pm25") is None:
                raw_aqi = float(np.clip(reading["aqi"], 0, 500))
                pm25 = aqi_to_pm25(raw_aqi)
            else:
                pm25 = float(np.clip(reading["pm25"], 0, 500))
                raw_aqi = pm25_to_aqi(pm25)          # dataset AQI is derived from RAW pm25

            raw = {"pm25": pm25,
                   "pm10": float(reading["pm10"]) if reading.get("pm10") is not None else pm25 * 1.5,
                   # the node only measures particulates (+T/H): other gases carried forward
                   "no2": last["no2"], "o3": last["o3"], "co": last["co"], "so2": last["so2"]}
            cal = self.calibrator.apply(raw) if self.calibrator else dict(raw)
            noise_pct = abs(raw["pm25"] - cal["pm25"]) / max(raw["pm25"], 1e-6) * 100

            rt.sim_time = rt.sim_time + pd.Timedelta(hours=1)
            row = {"timestamp": rt.sim_time, **{k: cal[k] for k in POLLUTANTS}, "aqi": raw_aqi}
            rt.history.append(row)
            rt.ticks += 1

            # score the previous forecast against what actually happened
            rt.chart.append({"t": rt.sim_time.strftime("%d %b %H:%M"), "actual": round(raw_aqi, 1),
                             "predicted": None if rt.last_forecast is None else round(rt.last_forecast, 1)})

            pred, model_name = self._forecast(rt)
            rt.last_forecast = pred

            decision = rules.evaluate(raw_aqi, pred, outdoor["aqi"], rt.actuation)
            rt.actuation = decision.state
            for ch in decision.changes:
                msg = f"{ch['device'].upper()} {ch['from']} -> {ch['to']}  ({ch['reason']})"
                self._log("ACTUATION", city, msg, **ch, indoor_now=round(raw_aqi, 1),
                          indoor_pred=round(pred, 1), outdoor=round(outdoor["aqi"], 1), trigger=decision.trigger)
            if decision.trigger == "predicted" and any(c["device"] in ("purifier", "ventilation") for c in decision.changes):
                self._log("PREDICTIVE", city, f"Forecast {pred:.0f} > now {raw_aqi:.0f}: acting BEFORE the spike")
            self._log("TICK", city, f"[{source}] AQI {raw_aqi:.0f} -> forecast {pred:.0f} (outdoor {outdoor['aqi']:.0f})")

            rt.node = {"node_id": reading.get("node_id", "ESP32_NODE_01"), "rssi": reading.get("rssi"),
                       "last_seen": datetime.now().strftime("%H:%M:%S"), "source": source,
                       "temperature": reading.get("temperature"), "humidity": reading.get("humidity")}

            cat_eff = aqi_category(max(raw_aqi, pred))
            state = {
                "city": city, "sim_time": str(rt.sim_time), "source": source, "tick": rt.ticks,
                "model": {"name": model_name, "horizon_hours": 1,
                          "dcae_active": bool(self.calibrator and self.calibrator.active)},
                "current": {"aqi": round(raw_aqi, 1), "category": aqi_category(raw_aqi),
                            "pm25": round(cal["pm25"], 1), "pm10": round(cal["pm10"], 1),
                            "no2": round(cal["no2"], 1), "o3": round(cal["o3"], 1),
                            "co": round(cal["co"], 2), "so2": round(cal["so2"], 1),
                            "temperature": reading.get("temperature"), "humidity": reading.get("humidity")},
                "outdoor": {"aqi": round(outdoor["aqi"], 1), "category": aqi_category(outdoor["aqi"])},
                "forecast": {"aqi": round(pred, 1), "category": aqi_category(pred),
                             "for_time": str(rt.sim_time + pd.Timedelta(hours=1)),
                             "delta": round(pred - raw_aqi, 1)},
                "actuation": {**decision.state.to_dict(), "reasons": decision.reasons,
                              "trigger": decision.trigger, "changed": bool(decision.changes)},
                "advisory": {"level": cat_eff, "message": ADVISORY[cat_eff],
                             "risk_pct": int(min(100, round(max(raw_aqi, pred) / 5))),
                             "blink": max(raw_aqi, pred) >= 300},
                "calibration": {"active": bool(self.calibrator and self.calibrator.active),
                                "pm25_adjust_pct": round(noise_pct, 2)},
                "node": rt.node,
            }
            rt.last_state = state
        for fn in self.listeners:
            try:
                fn(city, state)
            except Exception as e:                  # noqa: BLE001
                self._log("WARN", city, f"listener error: {e}")
        return self.state(city)

    def step_replay(self, city: str) -> dict:
        """Advance one hour using the dataset itself as the sensor (demo without hardware)."""
        city = normalize_city(city)
        with self.lock:
            nxt = self.cities[city].series.iloc[self.cities[city].cursor % len(self.cities[city].series)]
        return self.ingest({"city": city, "pm25": float(nxt["pm25"]), "pm10": float(nxt["pm10"]),
                            "node_id": "REPLAY"}, source="replay")

    def demo_aqi(self, city: str, aqi: float) -> dict:
        """Dashboard slider: force the indoor AQI (goes through the SAME pipeline)."""
        return self.ingest({"city": city, "aqi": aqi, "node_id": "DEMO_SLIDER"}, source="demo-slider")

    # ------------------------------------------------------------------ read side
    def state(self, city: str) -> dict:
        city = normalize_city(city)
        with self.lock:
            rt = self.cities[city]
            if rt.last_state is None:               # nothing ingested yet: report the seed hour
                last = rt.history[-1]
                a = rt.actuation.to_dict()
                st = {"city": city, "sim_time": str(rt.sim_time), "source": "seed", "tick": 0,
                      "model": {"name": "bilstm" if self.forecaster else "fallback-trend", "horizon_hours": 1,
                                "dcae_active": bool(self.calibrator and self.calibrator.active)},
                      "current": {**{k: round(last[k], 2) for k in POLLUTANTS}, "aqi": round(last["aqi"], 1),
                                  "category": aqi_category(last["aqi"]), "temperature": None, "humidity": None},
                      "outdoor": {"aqi": round(rt.outdoor_aqi, 1), "category": aqi_category(rt.outdoor_aqi)},
                      "forecast": None, "actuation": {**a, "reasons": [], "trigger": "none", "changed": False},
                      "advisory": {"level": aqi_category(last["aqi"]), "message": ADVISORY[aqi_category(last["aqi"])],
                                   "risk_pct": int(min(100, round(last["aqi"] / 5))), "blink": False},
                      "calibration": {"active": bool(self.calibrator and self.calibrator.active), "pm25_adjust_pct": 0},
                      "node": {}}
            else:
                st = dict(rt.last_state)
            chart = list(rt.chart)
            st["chart"] = {
                "labels": [c["t"] for c in chart] + ([(rt.sim_time + pd.Timedelta(hours=1)).strftime("%d %b %H:%M") + " (forecast)"]
                                                      if rt.last_forecast is not None else []),
                "actual": [c["actual"] for c in chart] + ([None] if rt.last_forecast is not None else []),
                "predicted": [c["predicted"] for c in chart] + ([round(rt.last_forecast, 1)] if rt.last_forecast is not None else []),
            }
            return st

    def recent_log(self, limit: int = 50, city: Optional[str] = None) -> List[dict]:
        with self.lock:
            items = [e for e in self.log if city is None or e["city"] in (None, city)]
            return items[:limit]

    def health(self) -> dict:
        return {"status": "ok",
                "forecaster": "bilstm" if self.forecaster else "fallback-trend",
                "forecaster_error": self.model_error,
                "dcae": bool(self.calibrator and self.calibrator.active),
                "dcae_error": self.calibrator.error if self.calibrator else "disabled",
                "cities": list(self.cities), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
