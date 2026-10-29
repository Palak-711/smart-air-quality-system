/*
 * Smart AQI Node  --  ESP32 simulation for Wokwi
 * ------------------------------------------------------------------
 * SENSE   : DHT22 (temperature, humidity) + potentiometer on GPIO34
 *           The potentiometer stands in for the particulate/gas sensor
 *           (Wokwi has no PM2.5 sensor; on real hardware this is the MQ-135 / PMS5003 analog pin).
 *           0 V .. 3.3 V  ->  ADC 0..4095  ->  PM2.5 0..160 ug/m3  (same range as the dataset)
 * COMMUNICATE: MQTT (PubSubClient) via the public broker. Wokwi's Wi-Fi is "Wokwi-GUEST".
 * ACT     : the backend publishes the actuation decision; this node drives
 *           2 LEDs (purifier LOW/HIGH) + 1 LED (air OK) + servo (smart window) + relay (exhaust fan).
 *
 * TOPICS  : <PREFIX>/telemetry  (this node  -> backend)
 *           <PREFIX>/control    (backend    -> this node)
 *
 * !! Change MQTT_PREFIX to something unique to your team, and use THE SAME value in the backend
 * !! (environment variable MQTT_PREFIX). The broker is public and shared with everyone.
 */
#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>

// ---------------------------------------------------------------- configuration
const char* WIFI_SSID   = "Wokwi-GUEST";
const char* WIFI_PASS   = "";
const char* MQTT_BROKER = "broker.hivemq.com";
const int   MQTT_PORT   = 1883;
const char* MQTT_PREFIX = "smartaqi/CHANGE_ME_team42";   // <-- make this unique!
const char* CITY        = "Delhi";                       // Delhi | Faridabad | Gurugram
const char* NODE_ID     = "ESP32_NODE_01";
const unsigned long PUBLISH_EVERY_MS = 5000;             // 1 message = 1 simulated hour (see README)

// ---------------------------------------------------------------- pins
#define PIN_DHT        4
#define PIN_SENSOR     34     // potentiometer wiper (ADC1, safe to use with Wi-Fi on)
#define PIN_LED_OK     33     // green : purifier OFF / air fine
#define PIN_LED_LOW    25     // blue  : purifier LOW
#define PIN_LED_HIGH   27     // red   : purifier HIGH
#define PIN_RELAY      26     // exhaust fan relay (HIGH = fan ON)
#define PIN_SERVO      18     // smart window: 0 deg = OPEN, 90 deg = CLOSED

DHT dht(PIN_DHT, DHT22);
Servo windowServo;
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

String topicTelemetry, topicControl;
unsigned long lastPublish = 0, lastReconnectTry = 0;

// ---------------------------------------------------------------- helpers
float readPm25() {
  int samples[7];
  for (int i = 0; i < 7; i++) { samples[i] = analogRead(PIN_SENSOR); delay(2); }
  for (int i = 0; i < 6; i++)                      // tiny insertion sort -> median rejects ADC spikes
    for (int j = i + 1; j < 7; j++)
      if (samples[j] < samples[i]) { int t = samples[i]; samples[i] = samples[j]; samples[j] = t; }
  return samples[3] * 160.0f / 4095.0f;
}

void applyOutputs(const char* purifier, const char* window, const char* fan) {
  digitalWrite(PIN_LED_OK,   strcmp(purifier, "OFF")  == 0);
  digitalWrite(PIN_LED_LOW,  strcmp(purifier, "LOW")  == 0);
  digitalWrite(PIN_LED_HIGH, strcmp(purifier, "HIGH") == 0);
  windowServo.write(strcmp(window, "CLOSED") == 0 ? 90 : 0);
  digitalWrite(PIN_RELAY, strcmp(fan, "ON") == 0 ? HIGH : LOW);
}

void onMessage(char* topic, byte* payload, unsigned int length) {
  StaticJsonDocument<384> doc;
  if (deserializeJson(doc, payload, length)) { Serial.println("[ctrl] bad JSON ignored"); return; }
  const char* city = doc["city"] | "";
  if (strcmp(city, CITY) != 0) return;                       // command for another city
  const char* purifier = doc["purifier"] | "OFF";
  const char* window   = doc["window"]   | "OPEN";
  const char* fan      = doc["fan"]      | "OFF";
  applyOutputs(purifier, window, fan);
  Serial.printf("[ctrl] AQI %.0f -> forecast %.0f (%s) | purifier=%s window=%s fan=%s\n",
                (float)(doc["aqi"] | 0.0f), (float)(doc["forecast"] | 0.0f),
                (const char*)(doc["level"] | "?"), purifier, window, fan);
}

void connectWifi() {
  Serial.print("Connecting Wi-Fi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);
  while (WiFi.status() != WL_CONNECTED) { delay(250); Serial.print("."); }
  Serial.printf("\nWi-Fi OK, IP %s\n", WiFi.localIP().toString().c_str());
}

bool connectMqtt() {
  String cid = String("aqi-node-") + String((uint32_t)esp_random(), HEX);   // unique id per boot
  if (!mqtt.connect(cid.c_str())) { Serial.printf("MQTT failed rc=%d\n", mqtt.state()); return false; }
  mqtt.subscribe(topicControl.c_str());
  Serial.printf("MQTT OK, subscribed to %s\n", topicControl.c_str());
  return true;
}

// ---------------------------------------------------------------- Arduino entry points
void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED_OK, OUTPUT); pinMode(PIN_LED_LOW, OUTPUT); pinMode(PIN_LED_HIGH, OUTPUT);
  pinMode(PIN_RELAY, OUTPUT);
  analogReadResolution(12);
  dht.begin();
  windowServo.attach(PIN_SERVO);
  applyOutputs("OFF", "OPEN", "OFF");                         // safe defaults at boot

  topicTelemetry = String(MQTT_PREFIX) + "/telemetry";
  topicControl   = String(MQTT_PREFIX) + "/control";
  connectWifi();
  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setCallback(onMessage);
  mqtt.setBufferSize(512);
  connectMqtt();
}

void loop() {
  if (!mqtt.connected() && millis() - lastReconnectTry > 3000) {   // non-blocking reconnect
    lastReconnectTry = millis();
    connectMqtt();
  }
  mqtt.loop();

  if (millis() - lastPublish >= PUBLISH_EVERY_MS) {
    lastPublish = millis();
    float pm25 = readPm25();
    float t = dht.readTemperature(), h = dht.readHumidity();

    StaticJsonDocument<256> doc;
    doc["node"] = NODE_ID;
    doc["city"] = CITY;
    doc["pm25"] = round(pm25 * 10) / 10.0;
    if (!isnan(t)) doc["temp"] = round(t * 10) / 10.0;        // omit instead of sending NaN
    if (!isnan(h)) doc["hum"]  = round(h * 10) / 10.0;
    doc["rssi"] = WiFi.RSSI();
    char buf[256];
    size_t n = serializeJson(doc, buf);

    if (mqtt.connected() && mqtt.publish(topicTelemetry.c_str(), (const uint8_t*)buf, n)) {
      Serial.printf("[tx] %s\n", buf);
    } else {
      Serial.println("[tx] publish failed (offline?) - will retry next cycle");
    }
  }
}
