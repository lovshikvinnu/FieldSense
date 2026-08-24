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

// NEVER call fillScreen() on a repaint.
//
// The first version redrew the whole panel once a second, background and all.
// There is no framebuffer between us and the ST7789 - every draw call lands on
// glass immediately - so a full clear-and-redraw is visible as a hard flicker,
// the screen emptying and refilling once a second. Splitting the paint in two
// fixes it: the chrome is written once and left alone, and each value clears
// only its own few pixels before reprinting.

// Static chrome: background, title, card shapes, fixed labels. Drawn once.
static void renderChrome() {
  tft.fillScreen(COL_BG);
  label(8, 8, "FIELDSENSE", COL_ACCENT, 2);

  drawCard(40, 26);                                  // field name
  drawCard(72, 58);                                  // headline status
  label(14, 80, "SOIL HEALTH", COL_DIM, 1);
  drawCard(138, 44);                                 // score
  label(14, 146, "SCORE", COL_DIM, 1);
  drawCard(190, 84);                                 // counts
  label(14, 198, "samples total",   COL_DIM, 1);
  label(14, 212, "valid",           COL_DIM, 1);
  label(14, 226, "rejected",        COL_DIM, 1);
  label(14, 240, "zones",           COL_DIM, 1);
  label(14, 254, "recommendations", COL_DIM, 1);
  drawCard(284, 28);                                 // provenance
  label(14, 292, "evidence", COL_DIM, 1);
}

// Clear just this value's box, then print into it. Width is generous enough
// for the longest value each field can hold.
static void putValue(int16_t x, int16_t y, int16_t w, int16_t h,
                     uint16_t bg, uint16_t colour, uint8_t size) {
  tft.fillRect(x, y, w, h, bg);
  tft.setCursor(x, y);
  tft.setTextColor(colour);
  tft.setTextSize(size);
}

static void putCount(int16_t y, int32_t value, uint16_t colour) {
  putValue(150, y, 80, 8, COL_CARD, colour, 1);
  if (value < 0) {
    tft.print("--");
  } else {
    tft.print(value);
  }
}

// Everything that can change. Called on new data, and once a second so the
// age counter stays truthful.
static void renderValues() {
  bool everReceived = recordCount > 0;
  uint32_t ageS = everReceived ? (millis() - lastRecordMs) / 1000 : 0;

  putValue(8, 28, PANEL_W - 16, 8, COL_BG,
           everReceived ? (ageS > 30 ? COL_WARN : COL_DIM) : COL_WARN, 1);
  if (!everReceived) {
    tft.print("waiting for data...");
  } else {
    tft.print("updated ");
    tft.print(ageS);
    tft.print("s ago  #");
    tft.print(recordCount);
  }

  putValue(14, 48, PANEL_W - 28, 8, COL_CARD, COL_TEXT, 1);
  tft.print(fieldName);

  putValue(14, 96, PANEL_W - 28, 16, COL_CARD, statusColour(), 2);
  tft.print(statusText);

  putValue(150, 146, 70, 8, COL_CARD, COL_TEXT, 1);
  if (healthScore < 0.0f) {
    tft.print("--");
  } else {
    tft.print(healthScore, 2);
  }

  // The bar reads from across a room; the number does not. Always clear the
  // full track first or a shrinking score would leave the old bar behind.
  tft.fillRect(14, 160, PANEL_W - 40, 8, COL_BG);
  if (healthScore >= 0.0f) {
    int16_t barW = (int16_t)((PANEL_W - 40) * healthScore);
    if (barW < 0) barW = 0;
    if (barW > PANEL_W - 40) barW = PANEL_W - 40;
    tft.fillRect(14, 160, barW, 8, statusColour());
  }

  putCount(198, totalSamples,    COL_TEXT);
  putCount(212, validSamples,    COL_GOOD);
  putCount(226, rejectedSamples, rejectedSamples > 0 ? COL_WARN : COL_DIM);
  putCount(240, zoneCount,       COL_TEXT);
  putCount(254, recCount,        COL_ACCENT);

  putValue(90, 292, PANEL_W - 104, 8, COL_CARD, COL_TEXT, 1);
  tft.print(evidence);

  putValue(14, 302, PANEL_W - 28, 8, COL_BG,
           offlineMode == 1 ? COL_GOOD : COL_BG, 1);
  if (offlineMode == 1) {
    tft.print("OFFLINE MODE");
  }
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

  // PAINT BEFORE THE LINK. tft.init() wakes the panel and lights the
  // backlight but leaves display RAM uninitialised, which reads as a blank
  // white screen. Bridge.begin() and Monitor.begin() both talk to the router
  // over RPC - the same path measured at ~595 ms per call, which can stall or
  // wedge outright. Anything drawn after them is not drawn at all when they
  // hang, and the only symptom is a white panel that says nothing.
  //
  // So the dashboard goes up first, reading "waiting for data...", and the
  // link is brought up underneath it. A white screen now means the SPI or
  // display init failed, which is a genuinely different fault.
  renderChrome();
  renderValues();

  Bridge.begin();
  Monitor.begin(115200);

  renderValues();
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

  // Values only - the chrome is already on the glass and redrawing it is what
  // caused the flicker. Once a second is enough for the age counter.
  static uint32_t lastPaint = 0;
  if (dirty || millis() - lastPaint > 1000) {
    dirty = false;
    lastPaint = millis();
    renderValues();
  }
}
