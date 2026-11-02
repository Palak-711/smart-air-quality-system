# Changelog & System Audit Fixes

## High Severity Fixes
- **aqi_realtime_simulation.py**: Converted encoding to UTF-8/LF. Standardized path resolution and replaced fixed multiplier with official CPCB mapping engine.
- **requirements.txt**: Added missing FastAPI, Uvicorn, Pydantic, Paho-MQTT, Pytest, and HTTPX dependencies. Pinned TensorFlow and Keras versions.
- **find_city_file**: Updated data search path to recursively check `data/cleaned/` for dataset CSV files.
- **Tracked Modules**: Added untracked `api/storage.py`, `api/validation.py`, test suite, and audit documentation into Git.
