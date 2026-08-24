// FieldSense - MCU-rendered dashboard for the 2.8" ST7789 panel.
//
// WHY THIS REPLACES PIXEL STREAMING
//
// frame_receiver.ino ships a full 240x320 RGB565 frame - 153,600 bytes - from
// the QRB2210 to this MCU. On the UNO Q that cannot work, and the numbers say
// so rather than any hunch:
//
//   * Serial here is Arduino_RouterBridge's Monitor, and every
//     Serial.available() costs ~595 ms whether or not data is waiting - it is
//     a mon/read RPC round trip, measured at 1.68 calls/second by
//     link_probe.ino over a 247-second run.
//   * That caps the link at roughly 512 bytes per 595 ms, about 860 B/s.
//     A single frame would take three minutes.
//
// So this sketch does not receive pixels. It receives VALUES - one short
// newline-terminated record, about 70 bytes - and draws the dashboard itself
// with Adafruit_GFX. Under a second even at the measured rate, and the panel
// stays readable when nothing arrives at all.
//
// RECORD FORMAT, newline-terminated, order-independent, unknown keys ignored:
//
//   FS|f=North Paddock|s=HEALTHY|h=0.79|n=5|v=5|r=0|z=2|c=4|e=LIMITED|o=1
//
//     f  field name          (text)
//     s  soil health status  (text, drives the status colour)
//     h  soil health score   (0..1)
//     n  total samples       v  valid samples      r  rejected samples
//     z  zone count          c  recommendation count
//     e  evidence level      (text)
//     o  offline mode        (1/0)
//
// Values persist until replaced, so a dropped update leaves the last good
// reading on screen rather than blanking it. The header line always shows
// link state and seconds since the last accepted record, so the panel never
// lies about how fresh it is.

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
#define TFT_LED    6   // D7 is MAX485_RE_DE for the RS485 soil bus - never here

static const uint16_t PANEL_W = 240;
static const uint16_t PANEL_H = 320;

// Deep slate, matching the dashboard HTML so the panel and the browser view
// read as the same product rather than two different tools.
static const uint16_t COL_BG     = 0x0861;
static const uint16_t COL_CARD   = 0x18E3;
static const uint16_t COL_TEXT   = ST77XX_WHITE;
static const uint16_t COL_DIM    = 0x8410;
static const uint16_t COL_GOOD   = 0x07E0;
static const uint16_t COL_WARN   = 0xFD20;
static const uint16_t COL_BAD    = 0xF800;
static const uint16_t COL_ACCENT = 0x05FF;

Adafruit_ST7789 tft = Adafruit_ST7789(&SPI, TFT_CS, TFT_DC, TFT_RST);

// ------------------------------------------------------------- panel state

static char     fieldName[24] = "FieldSense";
static char     statusText[16] = "NO DATA";
static char     evidence[16]  = "-";
static float    healthScore   = -1.0f;   // negative means "never received"
static int32_t  totalSamples  = -1;
static int32_t  validSamples  = -1;
static int32_t  rejectedSamples = -1;
static int32_t  zoneCount     = -1;
static int32_t  recCount      = -1;
static int32_t  offlineMode   = -1;

static uint32_t lastRecordMs  = 0;
static uint32_t recordCount   = 0;
static bool     dirty         = true;

static char     lineBuf[256];
static size_t   lineLen = 0;

// ------------------------------------------------------------- parsing

static void copyField(char *dst, size_t cap, const char *src) {
  size_t i = 0;
  while (src[i] && i < cap - 1) {
    dst[i] = src[i];
    i++;
  }
  dst[i] = '\0';
}

// Apply one key=value pair. Unknown keys are ignored rather than rejected, so
// the host can add fields without reflashing this sketch.
static void applyPair(const char *key, const char *value) {
  if (!strcmp(key, "f"))      copyField(fieldName, sizeof(fieldName), value);
  else if (!strcmp(key, "s")) copyField(statusText, sizeof(statusText), value);
  else if (!strcmp(key, "e")) copyField(evidence, sizeof(evidence), value);
  else if (!strcmp(key, "h")) healthScore     = atof(value);
  else if (!strcmp(key, "n")) totalSamples    = atol(value);
  else if (!strcmp(key, "v")) validSamples    = atol(value);
  else if (!strcmp(key, "r")) rejectedSamples = atol(value);
  else if (!strcmp(key, "z")) zoneCount       = atol(value);
  else if (!strcmp(key, "c")) recCount        = atol(value);
  else if (!strcmp(key, "o")) offlineMode     = atol(value);
}

// Split "FS|k=v|k=v|..." in place. Returns false if the record is not ours,
// so line noise on a shared link cannot corrupt the display.
static bool parseRecord(char *text) {
  if (strncmp(text, "FS|", 3) != 0) {
    return false;
  }

  char *cursor = text + 3;
  while (*cursor) {
    char *bar = strchr(cursor, '|');
    if (bar) *bar = '\0';

    char *eq = strchr(cursor, '=');
    if (eq) {
      *eq = '\0';
      applyPair(cursor, eq + 1);
    }

    if (!bar) break;
    cursor = bar + 1;
  }
  return true;
}

// ------------------------------------------------------------- drawing

static uint16_t statusColour() {
  if (!strcmp(statusText, "HEALTHY"))  return COL_GOOD;
  if (!strcmp(statusText, "DEGRADED")) return COL_WARN;
  if (!strcmp(statusText, "STRESSED")) return COL_WARN;
  if (!strcmp(statusText, "CRITICAL")) return COL_BAD;
  return COL_DIM;
}

static void drawCard(int16_t y, int16_t h) {
  tft.fillRoundRect(6, y, PANEL_W - 12, h, 4, COL_CARD);
}

static void label(int16_t x, int16_t y, const char *text, uint16_t colour, uint8_t size) {
  tft.setCursor(x, y);
  tft.setTextColor(colour);
  tft.setTextSize(size);
  tft.print(text);
}

static void statRow(int16_t y, const char *name, int32_t value, uint16_t colour) {
  label(14, y, name, COL_DIM, 1);
  tft.setCursor(150, y);
  tft.setTextColor(colour);
  tft.setTextSize(1);
  if (value < 0) {
    tft.print("--");
  } else {
    tft.print(value);
  }
}

static void render() {
  tft.fillScreen(COL_BG);

  // Title
  label(8, 8, "FIELDSENSE", COL_ACCENT, 2);

  // Link state - always honest about freshness.
  bool everReceived = recordCount > 0;
  uint32_t ageS = everReceived ? (millis() - lastRecordMs) / 1000 : 0;
  tft.setCursor(8, 28);
  tft.setTextSize(1);
  if (!everReceived) {
    tft.setTextColor(COL_WARN);
    tft.print("waiting for data...");
  } else {
    tft.setTextColor(ageS > 30 ? COL_WARN : COL_DIM);
    tft.print("updated ");
    tft.print(ageS);
    tft.print("s ago  #");
    tft.print(recordCount);
  }

  // Field name
  drawCard(40, 26);
  label(14, 48, fieldName, COL_TEXT, 1);

  // Headline status
  drawCard(72, 58);
  label(14, 80, "SOIL HEALTH", COL_DIM, 1);
  tft.setCursor(14, 96);
  tft.setTextColor(statusColour());
  tft.setTextSize(2);
  tft.print(statusText);

  // Score as a number plus a bar - the bar is what reads from a distance.
  drawCard(138, 44);
  label(14, 146, "SCORE", COL_DIM, 1);
  tft.setCursor(150, 146);
  tft.setTextColor(COL_TEXT);
  tft.setTextSize(1);
  if (healthScore < 0.0f) {
    tft.print("--");
  } else {
    tft.print(healthScore, 2);
  }
  if (healthScore >= 0.0f) {
    int16_t barW = (int16_t)((PANEL_W - 40) * healthScore);
    if (barW < 0) barW = 0;
    if (barW > PANEL_W - 40) barW = PANEL_W - 40;
    tft.fillRect(14, 160, PANEL_W - 40, 8, COL_BG);
    tft.fillRect(14, 160, barW, 8, statusColour());
  }

  // Sample counts
  drawCard(190, 84);
  statRow(198, "samples total",  totalSamples,    COL_TEXT);
  statRow(212, "valid",          validSamples,    COL_GOOD);
  statRow(226, "rejected",       rejectedSamples, rejectedSamples > 0 ? COL_WARN : COL_DIM);
  statRow(240, "zones",          zoneCount,       COL_TEXT);
  statRow(254, "recommendations", recCount,       COL_ACCENT);

  // Provenance footer. Evidence level and offline flag matter for trust, so
  // they get their own line rather than being buried.
  drawCard(284, 28);
  label(14, 292, "evidence", COL_DIM, 1);
  tft.setCursor(90, 292);
  tft.setTextColor(COL_TEXT);
  tft.setTextSize(1);
  tft.print(evidence);
  tft.setCursor(14, 302);
  tft.setTextColor(offlineMode == 1 ? COL_GOOD : COL_DIM);
  tft.print(offlineMode == 1 ? "OFFLINE MODE" : "");
}

// ------------------------------------------------------------- lifecycle

void setup() {
  pinMode(TFT_LED, OUTPUT);
  digitalWrite(TFT_LED, HIGH);
  delay(500);
  SPI.begin();

  tft.init(PANEL_W, PANEL_H);
  tft.setRotation(0);
  tft.invertDisplay(false);

  Bridge.begin();
  Monitor.begin(115200);

  render();
}

void loop() {
  // available() costs ~595 ms on this transport, so one call per pass and take
  // everything it offers. Never poll it in a tight inner loop.
  int avail = Serial.available();
  while (avail > 0) {
    int c = Serial.read();
    if (c < 0) break;
    avail--;

    if (c == '\n' || c == '\r') {
      if (lineLen > 0) {
        lineBuf[lineLen] = '\0';
        if (parseRecord(lineBuf)) {
          lastRecordMs = millis();
          recordCount++;
          dirty = true;
        }
        lineLen = 0;
      }
    } else if (lineLen < sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = (char)c;
    } else {
      lineLen = 0;   // overlong line: drop it rather than truncate into a parse
    }
  }

  // Repaint on new data, and once a second otherwise so the age counter stays
  // truthful without burning SPI bandwidth.
  static uint32_t lastPaint = 0;
  if (dirty || millis() - lastPaint > 1000) {
    dirty = false;
    lastPaint = millis();
    render();
  }
}
