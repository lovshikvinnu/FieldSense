// FieldSense - UNO Q link probe. Measures the RouterBridge Monitor link and
// nothing else. No frame protocol, no CRC, and above all NO WRITES.
//
// WHY THIS EXISTS
//
// Three theories about why frame_receiver.ino stalls have each died on
// hardware, and each cost a reflash cycle to disprove:
//
//   1. The 512-byte RingBufferN in monitor.h was too small for 4096-byte
//      chunks. Killed: 256-byte chunks failed identically.
//   2. Holding one SPI transaction across the frame starved the Zephyr thread
//      serving the RPC. Killed: taking the bus per chunk changed nothing.
//   3. A mid-frame Serial.write() broke the next mon/read. Weakened: with
//      protocol v2 the MCU never writes, and the header still did not arrive.
//
// Every one of those was inferred from a single bit of evidence - the frame
// either landed or it did not. This sketch replaces inference with a live
// readout: what Serial.available() actually returns, how many bytes have
// actually arrived, when the first one showed up, and whether the Monitor
// still claims to be connected.
//
// It deliberately never calls Serial.write(). If bytes arrive here but not in
// frame_receiver.ino, theory 3 is right after all. If bytes never arrive, the
// fault is upstream of anything the receiver does.
//
// Pair with: python3 tools/link_probe.py

#include <SPI.h>

#undef MOSI
#undef MISO
#undef SCK

#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>
#include <Arduino_RouterBridge.h>

#define TFT_CS    10
#define TFT_DC     9
#define TFT_RST    8
#define TFT_LED    6   // D7 is MAX485_RE_DE - never drive it from here

static const uint16_t PANEL_W = 240;
static const uint16_t PANEL_H = 320;

Adafruit_ST7789 tft = Adafruit_ST7789(&SPI, TFT_CS, TFT_DC, TFT_RST);

static uint8_t sink[512];

static uint32_t totalBytes    = 0;
static int32_t  lastAvail     = -1;
static int32_t  maxAvail      = 0;
static uint32_t firstByteMs   = 0;
static uint32_t lastByteMs    = 0;
static uint32_t availCalls    = 0;
static uint32_t reconnects    = 0;
static uint32_t bootMs        = 0;

static void line(int16_t y, const char *label, uint32_t value, uint16_t colour) {
  tft.fillRect(0, y, PANEL_W, 12, ST77XX_BLACK);
  tft.setCursor(4, y);
  tft.setTextColor(colour);
  tft.setTextSize(1);
  tft.print(label);
  tft.print(value);
}

static void repaint(bool connected) {
  tft.fillRect(0, 0, PANEL_W, 22, ST77XX_BLACK);
  tft.setCursor(4, 4);
  tft.setTextSize(2);
  tft.setTextColor(connected ? ST77XX_GREEN : ST77XX_RED);
  tft.print(connected ? "LINK UP" : "LINK DOWN");

  line(30,  "bytes:    ", totalBytes,                 ST77XX_WHITE);
  line(44,  "avail():  ", (uint32_t)(lastAvail < 0 ? 0 : lastAvail), ST77XX_WHITE);
  line(58,  "max avail:", (uint32_t)maxAvail,         ST77XX_CYAN);
  line(72,  "calls:    ", availCalls,                 ST77XX_WHITE);
  line(86,  "first@ms: ", firstByteMs,                ST77XX_YELLOW);
  line(100, "last@ms:  ", lastByteMs,                 ST77XX_YELLOW);
  line(114, "reconnect:", reconnects,                 ST77XX_MAGENTA);
  line(128, "uptime s: ", (millis() - bootMs) / 1000, ST77XX_WHITE);
}

void setup() {
  pinMode(TFT_LED, OUTPUT);
  digitalWrite(TFT_LED, HIGH);
  delay(500);
  SPI.begin();

  tft.init(PANEL_W, PANEL_H);
  tft.setRotation(0);
  tft.invertDisplay(false);
  tft.fillScreen(ST77XX_BLACK);

  Bridge.begin();
  Monitor.begin(115200);

  bootMs = millis();
  repaint(false);
}

void loop() {
  // operator bool() re-queries mon/connected whenever _connected is false, so
  // this doubles as the reconnect attempt. Counting the transitions tells us
  // whether the session is flapping rather than simply idle.
  static bool wasConnected = false;
  bool connected = (bool)Monitor;
  if (connected && !wasConnected) {
    reconnects++;
  }
  wasConnected = connected;

  int avail = Serial.available();
  availCalls++;
  lastAvail = avail;
  if (avail > maxAvail) {
    maxAvail = avail;
  }

  if (avail > 0) {
    size_t want = (size_t)avail;
    if (want > sizeof(sink)) {
      want = sizeof(sink);
    }
    int got = Serial.readBytes((char *)sink, want);
    if (got > 0) {
      if (totalBytes == 0) {
        firstByteMs = millis() - bootMs;
      }
      totalBytes += (uint32_t)got;
      lastByteMs = millis() - bootMs;
    }
  }

  // Throttled so the SPI writes cannot dominate the read loop - the whole
  // point is to measure the link, not the display.
  static uint32_t lastPaint = 0;
  if (millis() - lastPaint > 400) {
    lastPaint = millis();
    repaint(connected);
  }
}
