# Wokwi simulation – step by step

> The `diagram.json` and sketch were written without access to Wokwi, so **run it once and fix anything that is off**
> (a wire that did not snap, a pin label). The pin table below is the source of truth if a wire is missing.

## 1. Create the project
1. Go to **wokwi.com → New Project → ESP32** (Arduino).
2. Replace `sketch.ino` with `wokwi/sketch.ino`.
3. Open the `diagram.json` tab and paste `wokwi/diagram.json` (or add the parts by hand – table below).
4. Open `libraries.txt` tab (or Library Manager) and paste `wokwi/libraries.txt`.
5. In `sketch.ino` set `MQTT_PREFIX` to a **unique** value, e.g. `smartaqi/iot-grp7-2026`, and `CITY`.

## 2. Parts & wiring
| Part | Part pin | ESP32 pin | Role |
|---|---|---|---|
| DHT22 | VCC / GND / SDA | 3V3 / GND / **GPIO4** | temperature, humidity |
| Potentiometer | VCC / GND / SIG | 3V3 / GND / **GPIO34** | stand-in for MQ-135 / PM sensor (ADC1) |
| LED green + 220 Ω | anode | **GPIO33** | purifier OFF (air fine) |
| LED blue + 220 Ω | anode | **GPIO25** | purifier LOW |
| LED red + 220 Ω | anode | **GPIO27** | purifier HIGH |
| Relay module | VCC / GND / IN | VIN / GND / **GPIO26** | exhaust fan (HIGH = ON) |
| Servo | V+ / GND / PWM | VIN / GND / **GPIO18** | smart window (0° open, 90° closed) |

Wokwi has no PM2.5 sensor, and its gas-sensor part is not an MQ-135, so the potentiometer is the standard stand-in.
Mapping: ADC 0–4095 → PM2.5 0–160 µg/m³ (the dataset's range). On real hardware, replace `readPm25()` with an MQ-135 /
PMS5003 calibration curve. Do not call the MQ-135 a PM2.5 sensor in the report: it senses gases (NH₃, CO₂, benzene…).

## 3. Run it
1. Start the backend with the **same** prefix: `MQTT_PREFIX=smartaqi/iot-grp7-2026 uvicorn api.main:app --port 8000`.
2. Click ▶ in Wokwi. Serial monitor shows `Wi-Fi OK`, `MQTT OK`, then `[tx] {...}` every 5 s and `[ctrl] ...` replies.
3. Open the dashboard. Check `GET /api/health` → `mqtt.connected: true`.
4. Turn the potentiometer: low = clean, high = spike. Watch LEDs, servo, relay and the dashboard change together.

## 4. Troubleshooting
| Symptom | Fix |
|---|---|
| Stuck on `Connecting Wi-Fi...` | Keep SSID `Wokwi-GUEST`, empty password, channel 6 (already in code). |
| `MQTT failed rc=-2` | Broker unreachable / busy: change `MQTT_BROKER` to `test.mosquitto.org` (backend too: `MQTT_BROKER`). |
| No `[ctrl]` lines | Prefix mismatch between sketch and backend, or `CITY` differs from the city the backend replies for. |
| Dashboard shows other people's data | Your prefix is not unique – change it. Public broker = shared. |
| `/api/health` → `mqtt.connected:false` | Server has no internet / firewall; use `POST /api/ingest` as a fallback. |

## 5. Demo script (2 minutes)
1. Pot at 25 % → green LED, window open, fan off.
2. Raise the pot **gradually** (a rising trend). Whenever the forecast is above the current value, the rule engine acts on the forecast and the log prints `PREDICTIVE` – that is the proactive moment. (The Bi-LSTM is mean-reverting: after a sudden jump its forecast can be *lower* than now; then the rule engine reacts to the current value instead. Know this before the demo.)
3. Pot at 100 % → red LED, servo closes the window, banner blinks, log shows `PREDICTIVE`/`ACTUATION`.
4. Dashboard city → Faridabad (change `CITY` in the sketch for hardware; the slider works for any city).
