/*
 * Shepherd Clone - Microcontroller firmware (Arduino / STM32duino)
 *
 * Protocol (one JSON object per line, 115200 baud):
 *   {"type":"MOVE","x":150.0,"y":-40.0,"z":80.0}   -> coordinates in mm
 *   {"type":"GRIPPER","state":"OPEN" | "CLOSE"}
 * Replies:
 *   "READY" once after boot, "DONE" after each finished command, "ERR <reason>" on failure.
 *
 * Requires the ArduinoJson library (v7) from the Library Manager.
 * moveTo() is the only hardware specific part: fill in your arm's kinematics there.
 */
#include <ArduinoJson.h>
#include <Servo.h>

// ---- Hardware configuration ----
const int GRIPPER_SERVO_PIN = 9;
const int GRIPPER_OPEN_ANGLE = 90;
const int GRIPPER_CLOSED_ANGLE = 20;
const unsigned long GRIPPER_MOVE_MS = 500;

// ---- Workspace limits in mm (reject anything outside) ----
const float X_MIN = -250, X_MAX = 250;
const float Y_MIN = 0, Y_MAX = 300;
const float Z_MIN = 0, Z_MAX = 200;

const size_t LINE_MAX = 128;
char line[LINE_MAX];
size_t lineLen = 0;
bool lineOverflow = false;

Servo gripper;

// Move the tool tip to (x, y, z) in mm and return only when the motion is finished.
// Replace the body with your robot's inverse kinematics + motor control
// (stepper drivers, servos, or G-code to a motion controller).
bool moveTo(float x, float y, float z) {
  // TODO: inverse kinematics and motor control for your arm
  delay(500);  // Placeholder for the motion time
  return true;
}

void setGripper(bool open) {
  gripper.write(open ? GRIPPER_OPEN_ANGLE : GRIPPER_CLOSED_ANGLE);
  delay(GRIPPER_MOVE_MS);
}

bool inRange(float v, float lo, float hi) {
  return v >= lo && v <= hi;
}

void handleCommand(const char* json) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, json);
  if (err) {
    Serial.print("ERR bad json: ");
    Serial.println(err.c_str());
    return;
  }

  const char* type = doc["type"] | "";

  if (strcmp(type, "MOVE") == 0) {
    if (!doc["x"].is<float>() || !doc["y"].is<float>() || !doc["z"].is<float>()) {
      Serial.println("ERR MOVE needs x, y, z");
      return;
    }
    float x = doc["x"], y = doc["y"], z = doc["z"];
    if (!inRange(x, X_MIN, X_MAX) || !inRange(y, Y_MIN, Y_MAX) || !inRange(z, Z_MIN, Z_MAX)) {
      Serial.println("ERR target outside workspace");
      return;
    }
    if (!moveTo(x, y, z)) {
      Serial.println("ERR move failed");
      return;
    }
    Serial.println("DONE");

  } else if (strcmp(type, "GRIPPER") == 0) {
    const char* state = doc["state"] | "";
    if (strcmp(state, "OPEN") == 0) {
      setGripper(true);
    } else if (strcmp(state, "CLOSE") == 0) {
      setGripper(false);
    } else {
      Serial.println("ERR unknown gripper state");
      return;
    }
    Serial.println("DONE");

  } else {
    Serial.println("ERR unknown command type");
  }
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {}  // Wait for native USB boards
  gripper.attach(GRIPPER_SERVO_PIN);
  setGripper(true);
  Serial.println("READY");
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\r') continue;

    if (c == '\n') {
      line[lineLen] = '\0';
      if (lineOverflow) {
        Serial.println("ERR line too long");
      } else if (lineLen > 0) {
        handleCommand(line);
      }
      lineLen = 0;
      lineOverflow = false;
    } else if (lineLen < LINE_MAX - 1) {
      line[lineLen++] = c;
    } else {
      lineOverflow = true;
    }
  }
}
