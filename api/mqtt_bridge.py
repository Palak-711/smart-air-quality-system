"""
api/mqtt_bridge.py  --  MQTT link between the (Wokwi) ESP32 node and the backend
===============================================================================
    ESP32 --publish--> <prefix>/telemetry  --> Engine.ingest()
    ESP32 <--command-- <prefix>/control    <-- Engine (after every tick)

Wokwi's ESP32 can reach the internet through its built-in "Wokwi-GUEST" Wi-Fi, but it cannot
reach `localhost`. So both sides meet on a PUBLIC broker (default: broker.hivemq.com).

!! A public broker is shared by everybody. Use a UNIQUE topic prefix (set MQTT_PREFIX) or you will
!! receive other people's messages. Never publish anything private.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Optional

from api.engine import Engine

BROKER = os.environ.get("MQTT_BROKER", "broker.hivemq.com")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
PREFIX = os.environ.get("MQTT_PREFIX", "smartaqi/CHANGE_ME_team42")


class MqttBridge:
    def __init__(self, engine: Engine, broker: str = BROKER, port: int = PORT, prefix: str = PREFIX):
        self.engine, self.broker, self.port, self.prefix = engine, broker, port, prefix.rstrip("/")
        self.t_telemetry = f"{self.prefix}/telemetry"
        self.t_control = f"{self.prefix}/control"
        self.connected = False
        self.last_error: Optional[str] = None
        self.client = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.last_error = "paho-mqtt not installed (pip install paho-mqtt)"
            return
        try:                                                    # paho-mqtt >= 2.0
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="",
                                      clean_session=True)
        except AttributeError:                                  # paho-mqtt 1.x
            self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        try:
            self.client.connect_async(self.broker, self.port, keepalive=30)
            self.client.loop_start()                            # background network thread
        except Exception as e:                                  # noqa: BLE001
            self.last_error = str(e)
            return
        self.engine.add_listener(self.publish_state)

    def stop(self) -> None:
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

    # ------------------------------------------------------------------ callbacks (v1 & v2 safe)
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        ok = (getattr(rc, "value", rc) == 0)
        self.connected = ok
        if ok:
            client.subscribe(self.t_telemetry, qos=0)
            self.engine._log("MQTT", None, f"Connected to {self.broker}, subscribed to {self.t_telemetry}")
        else:
            self.last_error = f"connect refused rc={rc}"

    def _on_disconnect(self, client, userdata, *args):
        self.connected = False
        self.engine._log("MQTT", None, "Disconnected from broker (auto-reconnect enabled)")

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("payload must be a JSON object")
            data = self._normalise(data)
            self.engine.ingest(data, source="esp32")
        except Exception as e:                                  # noqa: BLE001  never kill the loop
            self.engine._log("WARN", None, f"Bad MQTT payload ignored: {e}")

    @staticmethod
    def _normalise(d: dict) -> dict:
        """Accept short ESP32 keys (temp/hum/node) as well as long ones."""
        out = {
            "city": d.get("city", "Delhi"),
            "node_id": d.get("node") or d.get("node_id") or "ESP32_NODE_01",
            "temperature": d.get("temp", d.get("temperature")),
            "humidity": d.get("hum", d.get("humidity")),
            "rssi": d.get("rssi"),
        }
        if d.get("pm25") is not None:
            out["pm25"] = float(d["pm25"])
        elif d.get("adc") is not None:                          # raw ADC 0..4095 -> pm25 0..160
            out["pm25"] = float(d["adc"]) / 4095.0 * 160.0
        else:
            raise ValueError("need 'pm25' or 'adc'")
        return out

    # ------------------------------------------------------------------ outbound command
    def publish_state(self, city: str, state: dict) -> None:
        if not (self.client and self.connected):
            return
        a, cur, fc = state["actuation"], state["current"], state["forecast"]
        payload = {"city": city, "purifier": a["purifier"], "window": a["window"],
                   "fan": a["ventilation"], "aqi": cur["aqi"], "forecast": fc["aqi"],
                   "level": state["advisory"]["level"]}
        with self._lock:
            self.client.publish(self.t_control, json.dumps(payload), qos=0, retain=False)

    def status(self) -> dict:
        return {"enabled": self.client is not None, "connected": self.connected, "broker": self.broker,
                "telemetry_topic": self.t_telemetry, "control_topic": self.t_control,
                "error": self.last_error}
