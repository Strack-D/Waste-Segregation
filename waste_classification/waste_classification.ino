#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <ESP32Servo.h>
#include <Stepper.h>
#include <ArduinoJson.h>

// ===========================
// Select camera model in board_config.h
// ===========================
#include "board_config.h"

// ===========================
// Enter your WiFi credentials
// ===========================
const char *ssid = "Galaxy A52 B192";
const char *password = "xoxokvng";

#define IR_SENSOR 19
#define IN1 39
#define IN2 40
#define IN3 41
#define IN4 42
#define SERVO_PIN 38
#define BUZZER_PIN 21

const int stepsPerRevolution = 2048; // 28BYJ-48 full revolution
const int wasteCategories = 5;
const int stepsPerSlot = stepsPerRevolution / wasteCategories;
Stepper carousel(stepsPerRevolution, IN1, IN2, IN3, IN4); // IN1, IN2, IN3, IN4
// Define labels order (must match your trained model classes)
const char* wasteLabels[wasteCategories] = {"Plastic", "Paper", "Organic", "Metal", "Glass"};

Servo trapdoor;

// Timing & behavior tuning
const unsigned long irDebounceMs = 200;   // debounce IR trigger
const unsigned long postRetryDelayMs = 1000;
const unsigned long trapdoorOpenMs = 900; // how long trapdoor stays open
const int stepperSpeedRPM = 15;           // stepper rpm (tune between 5-15)
const int servoClosedAngle = 0;
const int servoOpenAngle = 90;

// Internal state
int currentSlot = 0;              // 0..(wasteCategories-1)
unsigned long lastIrTime = 0;

void beep(int times = 1, int durationMs = 100, int gapMs = 100) {
  for (int i = 0; i < times; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(durationMs);
    digitalWrite(BUZZER_PIN, LOW);
    if (i < times - 1) delay(gapMs);
  }
}

void beepWiFiConnected() {
  beep(1, 300);  // long beep
  delay(150);
  beep(1, 150);  // short beep
}

void beepWiFiFailed() {
  beep(3, 200, 150); // three slow beeps
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println("\n=== Waste Sorter Setup ===");

  // ---------- camera init ----------
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.frame_size = FRAMESIZE_CIF;
  config.pixel_format = PIXFORMAT_JPEG;  // for sending to classifier
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 8;
  config.fb_count = 2;

 if (!psramFound()) {
    config.frame_size = FRAMESIZE_QVGA;
    config.fb_location = CAMERA_FB_IN_DRAM;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
  } else {
    Serial.println("Camera initialized");
    sensor_t *s = esp_camera_sensor_get();
    if (s) {
      s->set_vflip(s, 1);
      s->set_whitebal(s, 1);
      s->set_exposure_ctrl(s, 1);
      s->set_gain_ctrl(s, 1);
      s->set_brightness(s, 1);
      s->set_saturation(s, 0);
    }
  }

  // ---------- WiFi ----------
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);

  Serial.print("Connecting to WiFi");
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
    Serial.print(".");
    delay(500);
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi connected, IP: ");
    Serial.println(WiFi.localIP());
    beepWiFiConnected();
  } else {
      Serial.println("\nConnection failed! (will attempt reconnect later)");
      beepWiFiFailed();
  }

  // ---------- actuators ----------
  carousel.setSpeed(stepperSpeedRPM);
  trapdoor.setPeriodHertz(50); // servo refresh
  trapdoor.attach(SERVO_PIN, 500, 2500); // SG90 pulse bounds: 500-2500us
  pinMode(IR_SENSOR, INPUT);
  trapdoor.write(servoClosedAngle);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // set initial currentSlot to 0 (assume starting home)
  currentSlot = 0;
  Serial.println("Setup complete");
}


void loop() {
  // Read IR sensor with simple debounce
  int irVal = digitalRead(IR_SENSOR);
  // Assuming IR goes LOW when waste present (adjust as needed)
  if (irVal == LOW) {
    if (millis() - lastIrTime > irDebounceMs) {
      lastIrTime = millis();
      Serial.println("IR: Waste detected -> capture & classify");
      beep(2, 100, 50); // two quick beeps
      handleWasteDetected();
    }
  }
}

void handleWasteDetected() {
  // Ensure WiFi connected (try reconnect if not)
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected, attempting reconnect...");
    WiFi.disconnect();
    WiFi.reconnect();
    unsigned long waitStart = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - waitStart < 5000) {
      delay(200);
    }
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("WiFi still down; skipping classification this cycle");
      beepWiFiFailed();
      return;
    } else {
      Serial.println("WiFi reconnected");
      beepWiFiConnected();
    }
  }

  // Capture frame
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed; aborting this cycle");
    return;
  }

  // POST image to Render classification endpoint
  String url = "https://waste-segregation-qmhl.onrender.com/classify";
  HTTPClient http;
  http.begin(url);
  http.addHeader("Content-Type", "image/jpeg");

  int httpCode = http.POST(fb->buf, fb->len);
  if (httpCode > 0) {
    String resp = http.getString();
    Serial.printf("HTTP %d response: %s\n", httpCode, resp.c_str());// 0=Plastic, 1=Paper, 2=Organic, 3=Metal, 4=Glass
    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, resp);
    if (error) {
        Serial.println("JSON parse failed!");
        return;
    }
    const char* predictedLabel = doc["label"];  // e.g. "Organic"
    int labelIndex = -1;

    // Match received string against your known labels
    for (int i = 0; i < wasteCategories; i++) {
      if (strcmp(predictedLabel, wasteLabels[i]) == 0) {
        labelIndex = i;
        break;
      }
    }

    if (labelIndex == -1) {
      Serial.printf("Classifier returned unknown label: %s\n", predictedLabel);
    } else {
      Serial.printf("Mapped label '%s' to slot %d\n", predictedLabel, labelIndex);
      sortWaste(labelIndex);
    }
  } else {
    Serial.printf("HTTP POST failed, code=%d\n", httpCode);
  }

  http.end();
  esp_camera_fb_return(fb);
}

void sortWaste(int label) {
  Serial.printf("Sorting to label %d (current %d)\n", label, currentSlot);
  beep(1, 300); // long beep to signal sorting start

  // compute relative steps (shortest path optional; here we do direct shortest path)
  int delta = label - currentSlot;

  // use shortest rotation direction around circular carousel
  if (abs(delta) > wasteCategories / 2) {
    // wrap-around
    if (delta > 0) delta = delta - wasteCategories;
    else delta = delta + wasteCategories;
  }

  long stepsToMove = (long)delta * stepsPerSlot;
  if (stepsToMove != 0) {
    Serial.printf("Stepping %ld steps to slot %d\n", stepsToMove, label);
    carousel.step(stepsToMove);
    delay(100); // small settle time
  } else {
    Serial.println("Already at target slot (no stepper move)");
  }

  trapdoor.write(servoOpenAngle); // Open trapdoor
  delay(trapdoorOpenMs);
  trapdoor.write(servoClosedAngle); // Close trapdoor

  currentSlot = label;
  Serial.println("Waste sorted");
  beep(3, 80, 50); // three short beeps to signal completion
}