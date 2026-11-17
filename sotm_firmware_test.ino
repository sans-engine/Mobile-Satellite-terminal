// SoTM test firmware v0.1 - STM32F407G-DISC1 (Arduino IDE + STM32duino)
// Speaks the protocol in protocol.py:
//   PING | MODE,x | AZEL,az,el | SAT,x | SITE,lat,lon,alt,off | START | STOP
// and sends T,... telemetry 20 times per second.
// The axes and the IMU are SIMULATED. No motors or sensors are needed.
// Green LED (PD12) is on while the state is TRACK.

const int LED_LOCK = PD12;
const unsigned long STEP_MS = 50;      // 20 Hz
const float SLEW_SPEED = 40.0;         // deg/s

String line;
String mode = "SAT";
String state = "IDLE";
String sat = "4B";
float lat = 36.90, lon = 30.70, alt = 30.0, off = 0.0;
float manAz = 0.0, manEl = 30.0;
float actAz = 0.0, actEl = 0.0;
unsigned long nextStep = 0;

float wrap180(float a) {
  while (a > 180.0) a -= 360.0;
  while (a < -180.0) a += 360.0;
  return a;
}

// idx-th comma separated number of s
float field(const String &s, int idx) {
  int start = 0;
  for (int i = 0; i < idx; i++) {
    start = s.indexOf(',', start);
    if (start < 0) return 0;
    start++;
  }
  int end = s.indexOf(',', start);
  if (end < 0) end = s.length();
  return s.substring(start, end).toFloat();
}

// commanded azimuth/elevation for the current mode
void command(float &az, float &el) {
  if (mode == "SAT") {
    float satLon = (sat == "5A") ? 31.0 : 50.0;   // degrees East, verify
    float d = (satLon - lon) * DEG_TO_RAD;
    float phi = lat * DEG_TO_RAD;
    float cg = cos(phi) * cos(d);
    float sg = sqrt(max(1.0f - cg * cg, 1e-9f));
    el = atan2(cg - 0.151264f, sg) * RAD_TO_DEG;
    az = 180.0f - atan2(sin(d), cos(d) * sin(phi)) * RAD_TO_DEG - off;
    az = fmod(az + 720.0f, 360.0f);
  } else if (mode == "TGT") {
    az = 0.0;     // placeholder target direction
    el = 30.0;
  } else {
    az = manAz;
    el = manEl;
  }
}

void handle(String s) {
  s.trim();
  if (s.length() == 0) return;
  if (s == "PING") {
    Serial.println("PONG");
    return;
  }
  int c = s.indexOf(',');
  String cmd = (c < 0) ? s : s.substring(0, c);
  String rest = (c < 0) ? "" : s.substring(c + 1);

  if (cmd == "MODE") {
    mode = rest;
    if (state != "IDLE") state = "SLEW";
  } else if (cmd == "AZEL") {
    manAz = field(rest, 0);
    manEl = field(rest, 1);
    if (mode == "MAN" && state != "IDLE") state = "SLEW";
  } else if (cmd == "SAT") {
    sat = rest;
  } else if (cmd == "SITE") {
    lat = field(rest, 0);
    lon = field(rest, 1);
    alt = field(rest, 2);
    off = field(rest, 3);
  } else if (cmd == "START") {
    state = "SLEW";
  } else if (cmd == "STOP") {
    state = "IDLE";
  } else {
    Serial.println("ERR");
    return;
  }
  Serial.println("OK");
}

void stepSim(unsigned long ms) {
  float t = ms / 1000.0;
  float ca, ce;
  command(ca, ce);

  if (state == "SLEW") {
    float da = wrap180(ca - actAz);
    float de = ce - actEl;
    float n = max(fabs(da), fabs(de));
    if (n < 0.3) {
      state = "TRACK";
    } else {
      float k = min(1.0f, SLEW_SPEED * STEP_MS / 1000.0f / n);
      actAz = fmod(actAz + da * k + 360.0f, 360.0f);
      actEl += de * k;
    }
  }
  if (state == "TRACK") {
    float e = 0.15 * sin(2 * PI * t / 3.0);
    actAz = fmod(ca + e + 360.0f, 360.0f);
    actEl = ce - e;
  }
  digitalWrite(LED_LOCK, state == "TRACK" ? HIGH : LOW);

  float err = sqrt(sq(wrap180(ca - actAz)) + sq(ce - actEl));
  float w = 2 * PI / 10.0;                      // 10 s platform period
  float roll = 8 * sin(w * t);
  float pitch = 8 * sin(w * t + 1.0);
  float yaw = 2 * sin(w * t + 2.0);

  Serial.print("T,");
  Serial.print(ms);          Serial.print(',');
  Serial.print(mode);        Serial.print(',');
  Serial.print(state);       Serial.print(',');
  Serial.print(ca, 2);       Serial.print(',');
  Serial.print(ce, 2);       Serial.print(',');
  Serial.print(actAz, 2);    Serial.print(',');
  Serial.print(actEl, 2);    Serial.print(',');
  Serial.print(roll, 2);     Serial.print(',');
  Serial.print(pitch, 2);    Serial.print(',');
  Serial.print(yaw, 2);      Serial.print(',');
  Serial.print(err, 2);      Serial.print(',');
  Serial.println("0");
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_LOCK, OUTPUT);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      handle(line);
      line = "";
    } else if (c != '\r') {
      line += c;
    }
  }
  unsigned long now = millis();
  if (now >= nextStep) {
    nextStep += STEP_MS;
    if (now > nextStep + 500) nextStep = now + STEP_MS;   // catch up after a stall
    stepSim(now);
  }
}
