#define PIN_TCLK  14
#define PIN_TCS   27
#define PIN_TDIN  26
#define PIN_TDO   25
#define PIN_TIRQ  33

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("--- XPT2046 DIRECT BIT-BANG DIAGNOSTIC ---");

  pinMode(PIN_TCLK, OUTPUT);
  pinMode(PIN_TCS, OUTPUT);
  pinMode(PIN_TDIN, OUTPUT);
  pinMode(PIN_TDO, INPUT);
  pinMode(PIN_TIRQ, INPUT_PULLUP);

  digitalWrite(PIN_TCS, HIGH);
  digitalWrite(PIN_TCLK, LOW);
  digitalWrite(PIN_TDIN, LOW);
}

uint16_t xpt_read(uint8_t cmd) {
  uint16_t data = 0;

  digitalWrite(PIN_TCS, LOW);
  delayMicroseconds(2);

  // Send 8-bit Command
  for (int i = 7; i >= 0; i--) {
    digitalWrite(PIN_TDIN, (cmd >> i) & 0x01);
    digitalWrite(PIN_TCLK, HIGH);
    delayMicroseconds(2);
    digitalWrite(PIN_TCLK, LOW);
    delayMicroseconds(2);
  }

  // Read 12-bit ADC Response
  for (int i = 11; i >= 0; i--) {
    digitalWrite(PIN_TCLK, HIGH);
    delayMicroseconds(2);
    if (digitalRead(PIN_TDO)) {
      data |= (1 << i);
    }
    digitalWrite(PIN_TCLK, LOW);
    delayMicroseconds(2);
  }

  digitalWrite(PIN_TCS, HIGH);
  return data;
}

void loop() {
  int irqState = digitalRead(PIN_TIRQ);

  // Read X (0x90) and Y (0xD0) differential channels
  uint16_t rawX = xpt_read(0x90);
  uint16_t rawY = xpt_read(0xD0);

  Serial.printf("IRQ (Pen Down = 0): %d | Raw X: %4d | Raw Y: %4d\n", irqState, rawX, rawY);

  delay(200);
}