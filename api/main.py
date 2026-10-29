"""
api/main.py  --  FastAPI backend (Member 5)
==========================================
Run from the REPO ROOT (so `aqi_common.py`, `inference.py`, `models/` and `data/` are found):

    pip install -r requirements.txt
    uvicorn api.main:app --reload --port 8000

    Dashboard : http://localhost:8000/
    API docs  : http://localhost:8000/docs      (Swagger UI - great for the live demo)

Environment variables (all optional)
    AQI_MODEL_DIR   folder with the .keras/.joblib/.json/.h5 files   (default: <repo>/models)
    AQI_DATA_DIR    folder searched recursively for the city CSVs    (default: <repo>/data)
    AQI_SIM_START   simulated "now" inside the dataset               (default: 2023-11-01 00:00:00)
    MQTT_ENABLED    1/0                                              (default: 1)
    MQTT_BROKER, MQTT_PORT, MQTT_PREFIX                              (see api/mqtt_bridge.py)
"""
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.engine import Engine          # noqa: E402
from api.mqtt_bridge import MqttBridge  # noqa: E402

ENGINE: Optional[Engine] = None
BRIDGE: Optional[MqttBridge] = None


def eng() -> Engine:
    if ENGINE is None:
        raise HTTPException(503, "Engine not ready")
    return ENGINE


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ENGINE, BRIDGE
    ENGINE = Engine()                                   # loads CSVs, model, DCAE ONCE
    if os.environ.get("MQTT_ENABLED", "1") != "0":
        BRIDGE = MqttBridge(ENGINE)
        BRIDGE.start()
    yield
    if BRIDGE:
        BRIDGE.stop()


app = FastAPI(title="Smart AQI Predictor & Actuation API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------------------------ schemas
class SensorReading(BaseModel):
    """What the ESP32 node sends (same JSON as the MQTT telemetry message)."""
    node_id: str = "ESP32_NODE_01"
    city: str = "Delhi"
    pm25: Optional[float] = Field(None, ge=0, le=500, description="PM2.5 in ug/m3")
    adc: Optional[int] = Field(None, ge=0, le=4095, description="raw 12-bit ADC (alternative to pm25)")
    pm10: Optional[float] = Field(None, ge=0, le=1000)
    temperature: Optional[float] = Field(None, ge=-40, le=85)
    humidity: Optional[float] = Field(None, ge=0, le=100)
    rssi: Optional[int] = None

    @model_validator(mode="after")
    def _need_pm_or_adc(self):
        if self.pm25 is None and self.adc is None:
            raise ValueError("provide 'pm25' or 'adc'")
        return self


class DemoAQI(BaseModel):
    city: str = "Delhi"
    aqi: float = Field(..., ge=0, le=500)


class PredictRequest(BaseModel):
    city: str
    history: List[Dict[str, Any]] = Field(..., description="hourly rows: timestamp,pm25,pm10,no2,o3,co,so2,aqi")


# ------------------------------------------------------------------------------------ routes
@app.get("/api/health")
def health():
    h = eng().health()
    h["mqtt"] = BRIDGE.status() if BRIDGE else {"enabled": False}
    return h


@app.get("/api/cities")
def cities():
    return {"cities": list(eng().cities)}


@app.get("/api/state/{city}")
def get_state(city: str):
    """Everything the dashboard needs for one city (poll this every 1-2 s)."""
    try:
        return eng().state(city)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/ingest")
def ingest(reading: SensorReading):
    """HTTP twin of the MQTT telemetry topic - handy for curl/Postman tests without a broker."""
    d = reading.model_dump()
    if d["pm25"] is None:
        d["pm25"] = d["adc"] / 4095.0 * 160.0
    try:
        return eng().ingest(d, source="http")
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/predict")
def predict(req: PredictRequest):
    """Stateless forecast from a caller-supplied history (>= 47 consecutive hourly rows)."""
    e = eng()
    if e.forecaster is None:
        raise HTTPException(503, f"Bi-LSTM not loaded: {e.model_error}")
    try:
        return e.forecaster.predict(req.history, req.city)
    except ValueError as err:
        raise HTTPException(422, str(err))


@app.post("/api/demo/aqi")
def demo_aqi(body: DemoAQI):
    """Dashboard slider: forces the indoor AQI and runs the full predict -> actuate pipeline."""
    try:
        return eng().demo_aqi(body.city, body.aqi)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/sim/step")
def sim_step(city: str = Query("Delhi")):
    """Advance one simulated hour using the dataset as the sensor (demo without hardware)."""
    try:
        return eng().step_replay(city)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/log")
def get_log(limit: int = Query(50, ge=1, le=500), city: Optional[str] = None):
    """Audit trail of every actuation decision and system event."""
    return {"entries": eng().recent_log(limit, city)}


# ------------------------------------------------------------------------------------ dashboard
_dash = ROOT / "dashboard"
if _dash.is_dir():                                      # mounted LAST so /api/* keeps priority
    app.mount("/", StaticFiles(directory=_dash, html=True), name="dashboard")
