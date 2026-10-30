# Member 3 – Bi-LSTM AQI forecaster (1 hour ahead)

One shared Bi-LSTM for **Delhi, Faridabad, Gurugram** (city is a one-hot input).
Input: last 24 hourly readings -> output: AQI at the next hour.

## Files
| File | Purpose |
|---|---|
| `aqi_common.py` | Feature engineering shared by training **and** inference (no train/serve skew) |
| `train_bilstm.py` | Load -> features -> chronological split -> scale -> train -> evaluate -> save |
| `inference.py` | `predict_next_hour_aqi(history, city)` for FastAPI |
| `verify_inference.py` | Checks the inference path reproduces training-time predictions + error handling |
| `models/bilstm_aqi_1h.keras` | Trained model (push to `models/`) |
| `models/bilstm_aqi_scaler.joblib` | Feature scaler + target scaling + feature list |
| `models/bilstm_aqi_metadata.json` | Window, features, split dates, metrics, library versions |
| `reports/` | `metrics.json`, `test_predictions.csv`, plot |

## Run
```bash
pip install -r requirements.txt
python train_bilstm.py --data-dir data --out-dir models --reports-dir reports
python verify_inference.py --data-dir data
```
`--data-dir` picks one CSV per city by filename prefix (`delhi*`, `faridabad*`, `gurugram*`),
preferring names containing "calibrated" (so `*_fully_calibrated.csv` works as-is).
Required columns: `timestamp, pm25, pm10, no2, o3, co, so2, aqi`. If **every** city file also has
`temperature` and `humidity`, they are used automatically.
Training is resumable (`--resume`, `--time-budget SECONDS`) if your machine is slow.

## Leakage controls
- **Chronological split**, same calendar cut-offs for all cities: train < 2023-05-27, val < 2023-09-13 12:00, test = rest (to 2023-12-31). Asserted in code.
- Scalers fitted on **train rows only**.
- All rolling/diff features are **causal**; missing hours are forward-filled (max 3 h), never interpolated from the future, and imputed hours are never used as targets.
- Windows never cross city boundaries. A window's *target* decides its split; val/test inputs may look back into earlier data (past only, as in production).
- `aqi_category`, lat/lon, `year`, `day` are not used as features. Test split is used once, for final scoring.
- "Bi" in Bi-LSTM only reads the **past 24-hour window** in both directions; it never sees future hours.

## Results (test: 2023-09-13 -> 2023-12-31, 7,878 samples)
| Model | MAE | RMSE | R² |
|---|---|---|---|
| **Bi-LSTM** | **40.5** | **50.3** | **0.368** |
| Ridge (last step only) | 41.0 | 50.5 | 0.364 |
| Persistence (AQI = last hour) | 55.8 | 70.8 | -0.251 |

Per city (Bi-LSTM): Delhi R² 0.364 / MAE 41.2 · Faridabad 0.380 / 40.2 · Gurugram 0.360 / 40.2.
Validation (monsoon period): MAE 37.8, RMSE 47.7, R² 0.510.
Trained on `delhi_/faridabad_/gurgaon_fully_calibrated.csv`.

**Read this honestly:** the Bi-LSTM clearly beats persistence but is only on par with a linear model.
In these CSVs, AQI autocorrelation is ~0.68 at *every* lag from 1 to 24 h, i.e. a slow seasonal
signal plus large hour-to-hour noise, so roughly 0.4 R² is about what any model can extract.
Do not expect much higher scores from tuning; better inputs (real weather, real sensor continuity) would help more.

## FastAPI hand-off (Member 5)
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from inference import get_forecaster, predict_next_hour_aqi

app = FastAPI()
get_forecaster()  # load model + scaler once at startup

class Req(BaseModel):
    city: str
    history: list[dict]   # >= 47 consecutive hourly rows: timestamp, pm25, pm10, no2, o3, co, so2, aqi

@app.post("/predict")
def predict(r: Req):
    try:
        return predict_next_hour_aqi(r.history, r.city)
    except ValueError as e:
        raise HTTPException(422, str(e))
```
Set `AQI_MODEL_DIR` if `models/` is not next to `inference.py`.
Needs **47** consecutive hourly rows (24-hour window + 23 h to warm up the 24-hour rolling features).
Response: `{city, as_of, forecast_for, horizon_hours, predicted_aqi, aqi_category}`.

## Data note
In the `*_fully_calibrated.csv` files the `aqi` column is identical to the `*_cleaned.csv` files (only pollutant
columns were calibrated), and ~430 hours per city still have `aqi = 0` while PM2.5 >= 1.8. If Member 4 recomputes AQI
from the calibrated pollutants, re-run `train_bilstm.py` on the new files.

## 15- and 30-minute forecasts
The CSVs are **hourly**, so the model is trained and validated only for a 1-hour horizon. For shorter horizons:
```python
from inference import predict_aqi_horizons
predict_aqi_horizons(history, "Delhi", horizons_minutes=(15, 30, 60))
# CLI: python inference.py --csv data/delhi_fully_calibrated.csv --city Delhi --horizons 15 30 60
```
- **60 min**: the trained Bi-LSTM (`"validated": true`).
- **15 / 30 min**: linear interpolation between the last observed AQI and the 60-minute forecast
  (`"method": "linear_interpolation"`, `"validated": false`). There is no 15/30-minute ground truth in hourly data, so
  their accuracy cannot be measured. For real 15/30-minute models, retrain on sensor data recorded at that interval.

## Comparison with existing GitHub projects
`existing_work_compare.py`, `make_existing_charts.py` and `reports/fig4_*.png`, `fig5_*.png`:
Okes2024's Ridge / Random Forest / Gradient Boosting re-trained under our protocol are on par with the Bi-LSTM
(R-squared 0.350 to 0.372 vs 0.368). Their repo's R-squared of 0.96 to 0.99 is for a different task (same-hour AQI
from same-hour PM, synthetic data, random split); the same task on our data gives R-squared above 0.99.
The ampnics repo is an ESP8266 + MQ135 hardware logger with no ML model or reported metrics.

## 15- and 30-minute models trained on SIMULATED 15-minute data
The real CSVs are hourly. `subhourly.py` builds a **simulated** 15-minute series: every :00 value is the real hourly
reading (kept exactly); the :15/:30/:45 values are a straight line between two real hours plus a random bridge-shaped
wiggle (correlated across pollutants). Files:
`subhourly.py`, `train_subhourly.py`, `inference_subhourly.py`, `verify_subhourly.py`, `make_subhourly_chart.py`,
`models/bilstm_aqi_15_30min*.{keras,joblib,json}`, `reports/simulated_15min/*.csv`, `reports/fig6_15_30min_simulated.png`.

```bash
python train_subhourly.py --data-dir data --time-budget 200      # repeat with --resume until it finishes
python verify_subhourly.py
python inference_subhourly.py --hourly-csv data/delhi_fully_calibrated.csv --city Delhi
```
```python
from inference_subhourly import predict_15_30min     # history15: >= 119 rows at 15-minute spacing
predict_15_30min(history15, "Delhi")                 # -> forecasts for +15 and +30 minutes
```
One Bi-LSTM with two outputs; forecasts are issued from the top of each hour (a simulated :15/:30/:45 point already
points toward the next real hour, so using it as history would leak the future).

Test results (SIMULATED targets, 7,869 hours, same time split as the hourly model):
| Horizon | Method | MAE | RMSE | R-squared |
|---|---|---|---|---|
| 15 min | Persistence | 19.5 | 24.6 | 0.818 |
| 15 min | Interpolation (hourly Bi-LSTM) | 16.9 | 21.1 | 0.866 |
| 15 min | **Bi-LSTM 15/30** | 17.0 | 21.2 | 0.864 |
| 30 min | Persistence | 32.0 | 40.2 | 0.475 |
| 30 min | Interpolation (hourly Bi-LSTM) | 25.3 | 31.6 | 0.675 |
| 30 min | **Bi-LSTM 15/30** | 25.4 | 31.6 | 0.676 |

**How to read this:** these numbers describe how well a model learns the simulation, not real 15/30-minute air
quality. The simulated data is "straight line + noise", so the trained model ends up matching plain interpolation; the
"oracle" row in `reports/subhourly_metrics.json` shows the floor set by the simulated noise (MAE 13.7 / 15.9).
Replace the simulated data with real sensor data at 15-minute spacing and retrain to get real accuracy.
