// EOG Eye Movement Detection — version stable avec baseline dynamique
// BioAMP EXG Pill + Arduino Uno R3
//
// CORRECTIONS :
//   1. Baseline dynamique — se recalibre lentement au repos
//      evite les faux positifs quand le signal derive avec la temperature
//   2. Detection Up/Down uniquement (ce dont vous avez besoin)
//   3. Confirmation sur 5 echantillons consecutifs (50ms a 100Hz)
//   4. Cooldown 800ms entre deux gestes

#define CALIBRATE_MODE false

// Seuils — ajustez si necessaire apres calibration
#define UP_THRESH      90    // deviation au-dessus de la baseline → Up
#define DOWN_THRESH    90    // deviation en-dessous → Down
#define BLINK_THRESH  200    // spike tres large → Blink (ignore par Python)
#define CONFIRM_SAMPLES  5   // echantillons consecutifs requis
#define GESTURE_COOLDOWN_MS 800

// Baseline dynamique — se met a jour lentement quand signal est au repos
// alpha = 0.002 → environ 500 echantillons (5s) pour s'adapter completement
#define BASELINE_ALPHA 0.002

float vBaseline = 513.0;
float hBaseline = 508.0;

int countUp   = 0;
int countDown = 0;
unsigned long lastGestureTime = 0;

void setup() {
  Serial.begin(115200);
  // Initialiser la baseline avec la vraie valeur au demarrage
  long sumV = 0, sumH = 0;
  for (int i = 0; i < 50; i++) {
    sumV += analogRead(A0);
    sumH += analogRead(A1);
    delay(10);
  }
  vBaseline = sumV / 50.0;
  hBaseline = sumH / 50.0;
}

void loop() {
  int vRaw = analogRead(A0);
  int hRaw = analogRead(A1);

  if (CALIBRATE_MODE) {
    Serial.print(vRaw);
    Serial.print(",");
    Serial.println(hRaw);
    delay(10);
    return;
  }

  int vDev = vRaw - (int)vBaseline;
  int hDev = hRaw - (int)hBaseline;

  // ── Detection Up / Down ──────────────────────────────────────────────────
  if (vDev >= UP_THRESH) {
    countUp++;
    countDown = 0;
    // Pas de mise a jour baseline quand signal actif
  } else if (vDev <= -DOWN_THRESH || abs(vDev) >= BLINK_THRESH) {
    countDown++;
    countUp = 0;
  } else {
    // Signal au repos → mise a jour lente de la baseline
    countUp   = 0;
    countDown = 0;
    vBaseline = vBaseline * (1.0 - BASELINE_ALPHA) + vRaw * BASELINE_ALPHA;
    hBaseline = hBaseline * (1.0 - BASELINE_ALPHA) + hRaw * BASELINE_ALPHA;
  }

  // ── Emission du geste ────────────────────────────────────────────────────
  unsigned long now = millis();
  bool cooldownOk = (now - lastGestureTime) >= GESTURE_COOLDOWN_MS;
  String gesture = "0";

  if (cooldownOk) {
    if (countUp >= CONFIRM_SAMPLES) {
      gesture = "Up";
      countUp = 0;
      countDown = 0;
    } else if (countDown >= CONFIRM_SAMPLES) {
      gesture = "Down";
      countUp = 0;
      countDown = 0;
    }
  }

  if (gesture != "0") {
    lastGestureTime = now;
  }

  Serial.println(gesture);
  delay(10);
}
