/*
 * Smart AQI Node  --  ESP32 simulation for Wokwi (Audited & Fixed Version)
 * ------------------------------------------------------------------
 * SENSE    : DHT22 (temperature, humidity) + potentiometer on GPIO34
 *            0 V .. 3.3 V  ->  ADC 0..4095  ->  PM2.5 0..125 ug/m3 (Aligned with backend max FS)
 * COMMUNICATE: MQTT (PubSubClient) via broker. Wokwi Wi-Fi is "Wokwi-GUEST".
 * ACT      : Drives 3 LEDs (purifier OFF/LOW/HIGH) + Servo (smart window) + Relay (exhaust fan).
 * Edge Fallback : Uses official CPCB AQI sub-index and hysteresis when MQTT is offline.
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
const unsigned long PUBLISH_EVERY_MS = 5000;             // 1 message = 1 simulated hour

// ---------------------------------------------------------------- constants
const float PM25_FULL_SCALE = 125.0f; // Fix Finding #16: Aligned with backend full-scale ADC range

// ---------------------------------------------------------------- pins
#define PIN_DHT        4
#define PIN_SENSOR     34     // potentiometer wiper (ADC1)
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

// Edge state trackers for offline fallback
String currentPurifier = "OFF";
String currentWindow   = "OPEN";
String currentFan      = "OFF";

// ---------------------------------------------------------------- CPCB Mapping & Edge Logic
float calculateCpcbAqi(float pm25) {
  // Fix Finding #9: Official CPCB linear breakpoint sub-index for PM2.5
  if (pm25 <= 0.0f) return 0.0f;
  if (pm25 <= 30.0f) return (50.0f / 30.0f) * pm25;
  if (pm25 <= 60.0f) return 50.0f + (50.0f / 30.0f) * (pm25 - 30.0f);
  if (pm25 <= 90.0f) return 100.0f + (100.0f / 30.0f) * (pm25 - 60.0f);
  if (pm25 <= 120.0f) return 200.0f + (100.0f / 30.0f) * (pm25 - 90.0f);
  if (pm25 <= 250.0f) return 300.0f + (100.0f / 130.0f) * (pm25 - 120.0f);
  return 400.0f + (100.0f / 130.0f) * min(pm25 - 250.0f, 130.0f);
}

void applyEdgeFailsafe(float pm25) {
  float aqi = calculateCpcbAqi(pm25);

  // Purifier edge logic
  if (aqi > 200.0f) currentPurifier = "HIGH";
  else if (aqi > 100.0f) currentPurifier = "LOW";
  else if (aqi <= 90.0f) currentPurifier = "OFF";

  // Fix Finding #7: Window logic with hysteresis reset rule (prevents permanent latch)
  if (aqi > 150.0f) {
    currentWindow = "CLOSED";
  } else if (aqi < 120.0f) {
    currentWindow = "OPEN";
  }

  currentFan = "OFF"; // Fan disabled in standalone edge failsafe mode
}

// ---------------------------------------------------------------- helpers
float readPm25() {
  int samples[7];
  for (int i = 0; i < 7; i++) { samples[i] = analogRead(PIN_SENSOR); delay(2); }
  for (int i = 0; i < 6; i++)                               // insertion sort -> median filter
    for (int j = i + 1; j < 7; j++)
      if (samples[j] < samples[i]) { int t = samples[i]; samples[i] = samples[j]; samples[j] = t; }
  
  // Fix Finding #16: Scale using 125.0f maximum full-scale
  return samples[3] * PM25_FULL_SCALE / 4095.0f;
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

  currentPurifier = doc["purifier"] | "OFF";
  currentWindow   = doc["window"]   | "OPEN";
  currentFan      = doc["fan"]      | "OFF";
  
  applyOutputs(currentPurifier.c_str(), currentWindow.c_str(), currentFan.c_str());
  Serial.printf("[ctrl] AQI %.0f -> forecast %.0f (%s) | purifier=%s window=%s fan=%s\n",
                (float)(doc["aqi"] | 0.0f), (float)(doc["forecast"] | 0.0f),
                (const char*)(doc["level"] | "?"), currentPurifier.c_str(), currentWindow.c_str(), currentFan.c_str());
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
  bool isConnected = mqtt.connected();
  if (!isConnected && millis() - lastReconnectTry > 3000) {   // non-blocking reconnect
    lastReconnectTry = millis();
    isConnected = connectMqtt();
  }
  mqtt.loop();

  if (millis() - lastPublish >= PUBLISH_EVERY_MS) {
    lastPublish = millis();
    float pm25 = readPm25();
    float t = dht.readTemperature(), h = dht.readHumidity();

    // Fall back to edge rules if disconnected from backend
    if (!isConnected) {
      applyEdgeFailsafe(pm25);
      applyOutputs(currentPurifier.c_str(), currentWindow.c_str(), currentFan.c_str());
      Serial.printf("[edge] Offline mode active | PM2.5: %.1f -> Window: %s Purifier: %s\n",
                    pm25, currentWindow.c_str(), currentPurifier.c_str());
    }

    StaticJsonDocument<256> doc;
    doc["node"] = NODE_ID;
    doc["city"] = CITY;
    doc["pm25"] = round(pm25 * 10) / 10.0;
    if (!isnan(t)) doc["temp"] = round(t * 10) / 10.0;
    if (!isnan(h)) doc["hum"]  = round(h * 10) / 10.0;
    doc["rssi"] = WiFi.RSSI();
    char buf[256];
    size_t n = serializeJson(doc, buf);

    if (isConnected && mqtt.publish(topicTelemetry.c_str(), (const uint8_t*)buf, n)) {
      Serial.printf("[tx] %s\n", buf);
    } else {
      Serial.println("[tx] publish failed (offline?) - will retry next cycle");
    }
  }
}
