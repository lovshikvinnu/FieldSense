// FieldSense AI - display-only bench panel, 320x240 landscape.
//
// DERIVED FROM firmware/unoq/fieldsense_unoq.ino, which is the
// firmware the assembled unit actually runs. This variant drops the GPS
// receiver and the operator's START control and keeps only the panel, so the
// display path can be exercised on a bare board with no receiver attached and
// nobody pressing anything.
//
// KEEP THE RECORD PARSER IN STEP WITH THE UNIFIED SKETCH.
// tests/test_panel_record_contract.py compares applyPair() across both files
// and fails if they diverge, because a key handled in one and ignored in the
// other is a value that silently never appears on one of the two panels.
// tests/test_landscape_panel.py holds the two layouts to the same orientation
// for the same reason.
//
// The record format, the palette, the layout constants and the renderer are
// otherwise identical to the unified sketch; see its header for why the panel
// receives values rather than pixels, and why it is landscape.

#include <SPI.h>

#undef MOSI
#undef MISO
#undef SCK

#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>
#include <Arduino_RouterBridge.h>

#include <stdio.h>    // snprintf, used by every value the panel formats
#include <string.h>   // strcmp/strlen/strchr, used by the record parser

#define TFT_CS    10
#define TFT_DC     9
#define TFT_RST    8
#define TFT_LED    6   // D7 is MAX485_RE_DE for the RS485 soil bus - never here

// XPT2046 resistive touch, sharing the display's SPI bus.
//
// WIRING, AND WHY T_DO MUST BE ON A4
//
// On the UNO Q the hardware SPI is on the ANALOG header, not D11-D13. From the
// board's device tree, arduino_spi is spi2:
//
//     SCK   A5   PB13        MISO  A4   PB14        MOSI  A3   PB15
//
// The SPI peripheral samples MISO from PB14 and from nowhere else. Wiring the
// controller's T_DO to a general-purpose pin - D4 was tried - means the command
// byte clocks out correctly over the shared SCK/MOSI and the 12-bit reply lands
// on a pin the hardware never reads, so every channel returns 0 and the panel
// looks identical to one with no controller fitted.
//
// Bit-banging is not an escape: SCK and MOSI are held by SPI2 through Zephyr
// pinctrl, and claiming them as GPIO would take the display down with them.
//
//     T_CLK -> A5   shared with the display's SCK
//     T_DIN -> A3   shared with the display's MOSI
//     T_DO  -> A4   the hardware SPI MISO. The ST7789 is write-only and never
//                   uses MISO, so this pin is free for the touch controller.
//     T_CS  -> D5   dedicated
//     T_IRQ -> D2   dedicated
//
// D5 previously held an optional momentary START switch. That is gone: it was a
// fallback for a unit whose touch panel did not answer, and the board's own
// VOL+/VOL- keys cover that case from the Linux side without occupying a pin.
#define TOUCH_CS   5
#define TOUCH_IRQ  2

// TOUCH IS OFF BY DEFAULT, AND THE DEFAULT IS NOT TIMIDITY.
//
// The panel went white on the assembled unit at the moment touch became live -
// both the jumpers and this firmware's runtime polling arrived together, so
// either could be the cause. What is certain is the cost asymmetry: the panel
// is the only output an operator in a field has, and touch is the SECOND input
// path behind the board's own VOL+/VOL- keys, which work. Risking the first to
// gain the second is a bad trade in any state of that uncertainty.
//
// The specific mechanism this guards against is real, not hypothetical. With
// touch enabled, readTouchZ() runs on every pass of the 2 ms drain loop and
// opens an SPI transaction at 2 MHz on the same bus the ST7789 drives at
// 24 MHz. Every one of those reconfigures the Zephyr SPI controller mid-stream,
// hundreds of times a second, between display writes. A white panel is exactly
// what a display fed a corrupted transaction looks like.
//
// Set this to 1 only after the display has been confirmed good with the touch
// jumpers physically connected and this still at 0. That order matters: it is
// the only way to tell a wiring fault from a bus-contention fault, and the two
// need opposite fixes.
// Touch is IRQ-GATED, which is what makes it safe to enable at all.
//
// The previous attempt polled the XPT2046 over SPI on every pass of the 2 ms
// drain loop - hundreds of controller reconfigurations a second on the bus the
// ST7789 drives at 24 MHz, for data that is meaningless unless a finger is
// actually down. The panel went white.
//
// PENIRQ makes that unnecessary. It is an open-drain line, active low on
// pen-down, readable with a bare digitalRead, and it costs nothing. So the
// driver below polls the GPIO and touches the SPI bus ONLY while that line is
// low, at most once per TOUCH_SAMPLE_MS. With nobody touching the glass the
// touch subsystem issues no SPI at all, which is the normal case by a very
// wide margin.
//
// This is also simply how an XPT2046 is meant to be driven; the earlier polling
// loop was the anomaly.
#define TOUCH_ENABLED 1

// LANDSCAPE. The glass is 240x320; setRotation(1) presents it as 320x240 and
// every coordinate in this file is written against that.
static const uint16_t PANEL_W = 320;
static const uint16_t PANEL_H = 240;
static const uint8_t  PANEL_ROTATION = 1;

// Adafruit_GFX's built-in font is 6x8 px per character at size 1 and scales by
// integer multiples. Named here because every fit calculation below uses them.
static const uint8_t  CHAR_W = 6;
static const uint8_t  CHAR_H = 8;

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

// --------------------------------------------------------- landscape layout
//
// One place for every coordinate. A layout constant that appears twice is a
// layout constant that will disagree with itself after the first edit, and on
// this board finding out costs a ninety-second flash-and-look cycle.
//
//   0            HEADER    FIELDSENSE            SAMPLE 2 / 5     26
//   30           GPS       FIX  SAT 10  HDOP 1.2      updated 3s  22
//   56           ACTION    the one large operator instruction     48
//   108          SOIL      moisture / pH / EC / N / P / K         70
//   182          BAR       START target, or the field result      58
//
static const int16_t HEADER_Y   = 0,   HEADER_H = 26;
static const int16_t GPS_Y      = 30,  GPS_H    = 22;
static const int16_t ACTION_Y   = 56,  ACTION_H = 48;
static const int16_t SOIL_Y     = 108, SOIL_H   = 70;
static const int16_t BAR_Y      = 182, BAR_H    = 58;
static const int16_t MARGIN     = 6;

// Two columns inside the soil card, and four label/value rows in each.
static const int16_t SOIL_COL_A = MARGIN + 8;
static const int16_t SOIL_COL_B = PANEL_W / 2 + 6;
static const int16_t SOIL_ROW_H = 15;

// ------------------------------------------------------------- panel state

static char     fieldName[24]   = "FieldSense";
static char     statusText[16]  = "NO DATA";
static char     evidence[16]    = "-";
static char     workflowState[20] = "BOOT";
static char     actionLine[40]  = "STARTING";
static char     lastQuality[14] = "";
static float    healthScore     = -1.0f;   // negative means "never received"
static int32_t  totalSamples    = -1;
static int32_t  validSamples    = -1;
static int32_t  rejectedSamples = -1;
static int32_t  zoneCount       = -1;
static int32_t  recCount        = -1;
static int32_t  offlineMode     = -1;
static int32_t  sampleIndex     = -1;
static int32_t  plannedSamples  = -1;
static int32_t  distinctLocs    = -1;
static float    soilMoisture    = -1.0f;
static float    soilPh          = -1.0f;
static float    soilEc          = -1.0f;
static int32_t  soilN           = -1;
static int32_t  soilP           = -1;
static int32_t  soilK           = -1;

static uint32_t lastRecordMs  = 0;
static uint32_t recordCount   = 0;
static bool     dirty         = true;

// Redrawing the static chrome is what caused the black wipe (see renderChrome
// below), so it happens once at boot and again only when the bottom bar has to
// change shape - armed green button, or flat result strip.
static bool     barIsButton   = false;
static bool     barShapeKnown = false;

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
  else if (!strcmp(key, "t")) copyField(workflowState, sizeof(workflowState), value);
  else if (!strcmp(key, "a")) copyField(actionLine, sizeof(actionLine), value);
  else if (!strcmp(key, "q")) copyField(lastQuality, sizeof(lastQuality), value);
  else if (!strcmp(key, "h")) healthScore     = atof(value);
  else if (!strcmp(key, "n")) totalSamples    = atol(value);
  else if (!strcmp(key, "v")) validSamples    = atol(value);
  else if (!strcmp(key, "r")) rejectedSamples = atol(value);
  else if (!strcmp(key, "z")) zoneCount       = atol(value);
  else if (!strcmp(key, "c")) recCount        = atol(value);
  else if (!strcmp(key, "o")) offlineMode     = atol(value);
  else if (!strcmp(key, "i")) sampleIndex     = atol(value);
  else if (!strcmp(key, "m")) plannedSamples  = atol(value);
  else if (!strcmp(key, "d")) distinctLocs    = atol(value);
  else if (!strcmp(key, "w")) soilMoisture    = atof(value);
  else if (!strcmp(key, "p")) soilPh          = atof(value);
  else if (!strcmp(key, "k")) soilEc          = atof(value);
  else if (!strcmp(key, "x")) soilN           = atol(value);
  else if (!strcmp(key, "y")) soilP           = atol(value);
  else if (!strcmp(key, "j")) soilK           = atol(value);
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

// True while the workflow is waiting for the operator to press START. Only
// these two states arm the bottom bar; a press in any other state is noise.
static bool workflowArmed() {
  return !strcmp(workflowState, "READY") ||
         !strcmp(workflowState, "READY_NEXT_SAMPLE");
}

// ------------------------------------------------- GPS placeholders

// This sketch carries no receiver. The GPS strip still draws, so the layout is
// exercised exactly as it is on the assembled unit, but it reports the truth:
// there is nothing attached to report a fix.
static String latest_gps_csv = "NO_GPS_IN_THIS_SKETCH";
static const char *gpsSatsText() { return "--"; }
static const char *gpsHdopText() { return "--"; }

// The operator control lives in the unified sketch. Declared here because the
// renderer tells the operator when no touch controller answered, and a bench
// panel with no control at all should not raise that warning.
static bool touchPresent = true;

// ------------------------------------------------------------- drawing

static uint16_t statusColour() {
  if (!strcmp(statusText, "HEALTHY"))  return COL_GOOD;
  if (!strcmp(statusText, "GOOD"))     return COL_GOOD;
  if (!strcmp(statusText, "DEGRADED")) return COL_WARN;
  if (!strcmp(statusText, "STRESSED")) return COL_WARN;
  if (!strcmp(statusText, "MODERATE")) return COL_WARN;
  if (!strcmp(statusText, "POOR"))     return COL_BAD;
  if (!strcmp(statusText, "CRITICAL")) return COL_BAD;
  return COL_DIM;
}

static uint16_t qualityColour() {
  if (!strcmp(lastQuality, "VALID"))      return COL_GOOD;
  if (!strcmp(lastQuality, "SUSPICIOUS")) return COL_WARN;
  if (!strcmp(lastQuality, "RETRY"))      return COL_WARN;
  if (!strcmp(lastQuality, "REJECTED"))   return COL_BAD;
  return COL_DIM;
}

static void label(int16_t x, int16_t y, const char *text, uint16_t colour, uint8_t size) {
  tft.setCursor(x, y);
  tft.setTextColor(colour);
  tft.setTextSize(size);
  tft.print(text);
}

// Largest text size at which `text` fits inside `width`, floor of 1.
//
// This is what keeps the instruction line from clipping. "SAMPLE 1 SAVED" gets
// size 3 and reads across a field; "PLACE PROBE - PRESS START" gets size 2 and
// still fits on one line. Neither is truncated, and neither is hard-coded.
static uint8_t fitTextSize(const char *text, int16_t width, uint8_t maxSize) {
  size_t len = strlen(text);
  if (len == 0) return maxSize;
  for (uint8_t size = maxSize; size > 1; size--) {
    if ((int16_t)(len * CHAR_W * size) <= width) {
      return size;
    }
  }
  return 1;
}

// Draw `text` at a fixed left edge, truncated to the width it is given.
//
// Adafruit_GFX wraps by default: a string wider than the screen continues on
// the next line, which here would land on top of the band below. Every
// host-supplied string on this panel goes through this or drawCentered(), so
// no value the host sends can push another one off the glass.
static void drawClipped(int16_t x, int16_t y, int16_t w,
                        const char *text, uint16_t colour, uint8_t size) {
  size_t maxChars = (size_t)(w / (CHAR_W * size));
  size_t len = strlen(text);
  if (len > maxChars) len = maxChars;
  tft.setCursor(x, y);
  tft.setTextColor(colour);
  tft.setTextSize(size);
  for (size_t i = 0; i < len; i++) {
    tft.write(text[i]);
  }
}

// Draw `text` centred in a box, clipped rather than allowed to overflow it.
static void drawCentered(int16_t x, int16_t y, int16_t w, int16_t h,
                         const char *text, uint16_t colour, uint8_t maxSize) {
  uint8_t size = fitTextSize(text, w - 8, maxSize);
  size_t len = strlen(text);
  size_t maxChars = (size_t)((w - 8) / (CHAR_W * size));
  if (maxChars < 1) maxChars = 1;
  if (len > maxChars) len = maxChars;

  int16_t textW = (int16_t)(len * CHAR_W * size);
  int16_t textH = (int16_t)(CHAR_H * size);
  tft.setCursor(x + (w - textW) / 2, y + (h - textH) / 2);
  tft.setTextColor(colour);
  tft.setTextSize(size);
  for (size_t i = 0; i < len; i++) {
    tft.write(text[i]);
  }
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

// NEVER call fillScreen() on a periodic repaint.
//
// render() used to clear the whole panel and redraw it once a second. There is
// no framebuffer between this sketch and the ST7789 - every draw lands on glass
// immediately - so the clear is visible: at the library default 24 MHz a full
// clear is tens of milliseconds of blank panel, followed by the elements
// reappearing one at a time. Physically that reads as a black wipe sweeping the
// panel once per second, which is what was observed on hardware.
//
// The split below is the whole fix: chrome once, values per update.

// Static chrome: background, title, card shapes, fixed labels. Drawn once.
static void renderChrome() {
  tft.fillScreen(COL_BG);

  // Header band
  tft.fillRect(0, HEADER_Y, PANEL_W, HEADER_H, COL_CARD);
  label(MARGIN + 2, 5, "FIELDSENSE", COL_ACCENT, 2);
  tft.drawFastHLine(0, HEADER_H, PANEL_W, COL_DIM);

  // Soil card and its fixed labels. Two columns, because 320 px of width is
  // the whole reason this layout exists.
  tft.fillRoundRect(MARGIN, SOIL_Y, PANEL_W - 2 * MARGIN, SOIL_H, 4, COL_CARD);
  label(SOIL_COL_A, SOIL_Y + 6,                   "MOISTURE", COL_DIM, 1);
  label(SOIL_COL_A, SOIL_Y + 6 + SOIL_ROW_H,      "PH",       COL_DIM, 1);
  label(SOIL_COL_A, SOIL_Y + 6 + SOIL_ROW_H * 2,  "EC",       COL_DIM, 1);
  label(SOIL_COL_B, SOIL_Y + 6,                   "N",        COL_DIM, 1);
  label(SOIL_COL_B, SOIL_Y + 6 + SOIL_ROW_H,      "P",        COL_DIM, 1);
  label(SOIL_COL_B, SOIL_Y + 6 + SOIL_ROW_H * 2,  "K",        COL_DIM, 1);
  label(SOIL_COL_A, SOIL_Y + 6 + SOIL_ROW_H * 3,  "SAMPLES",  COL_DIM, 1);
  label(SOIL_COL_B, SOIL_Y + 6 + SOIL_ROW_H * 3,  "SITES",    COL_DIM, 1);
}

// The bottom bar changes shape, not just contents: a green START target when
// the workflow is armed, a flat strip otherwise. Redrawing that shape is the
// only chrome change after boot, and it happens on a state edge rather than on
// every repaint so it cannot reintroduce the wipe.
static void renderBarChrome(bool asButton) {
  if (asButton) {
    tft.fillRoundRect(MARGIN, BAR_Y, PANEL_W - 2 * MARGIN, BAR_H - 2, 6, COL_GOOD);
    tft.drawRoundRect(MARGIN, BAR_Y, PANEL_W - 2 * MARGIN, BAR_H - 2, 6, COL_TEXT);
  } else {
    tft.fillRoundRect(MARGIN, BAR_Y, PANEL_W - 2 * MARGIN, BAR_H - 2, 6, COL_CARD);
  }
  barIsButton = asButton;
  barShapeKnown = true;
}

static void putFloat(int16_t x, int16_t y, int16_t w, float value,
                     uint8_t decimals, uint16_t colour) {
  putValue(x, y, w, CHAR_H, COL_CARD, colour, 1);
  if (value < 0.0f) {
    tft.print("--");
  } else {
    tft.print(value, decimals);
  }
}

static void putInt(int16_t x, int16_t y, int16_t w, int32_t value, uint16_t colour) {
  putValue(x, y, w, CHAR_H, COL_CARD, colour, 1);
  if (value < 0) {
    tft.print("--");
  } else {
    tft.print(value);
  }
}

// Everything that can change. Called on new data, and once a second so the age
// counter stays truthful.
static void renderValues() {
  char buf[48];

  // Header right: which sample, out of how many. The counter an operator
  // checks before deciding whether to walk on.
  putValue(PANEL_W - 150, 5, 144, CHAR_H * 2, COL_CARD, COL_TEXT, 2);
  if (sampleIndex > 0 && plannedSamples > 0) {
    snprintf(buf, sizeof(buf), "SAMPLE %ld/%ld", (long)sampleIndex, (long)plannedSamples);
    int16_t width = (int16_t)(strlen(buf) * CHAR_W * 2);
    tft.setCursor(PANEL_W - MARGIN - 2 - width, 5);
    tft.print(buf);
  }

  // GPS strip. Fix state, satellites and HDOP come straight from this sketch's
  // own GGA parse - the host is never asked to tell the panel what the receiver
  // attached to this MCU is doing.
  putValue(MARGIN, GPS_Y, PANEL_W - 2 * MARGIN, CHAR_H, COL_BG, COL_DIM, 1);
  bool haveFix = (strncmp(latest_gps_csv.c_str(), "FIX_OK", 6) == 0);
  tft.setTextColor(haveFix ? COL_GOOD : COL_WARN);
  tft.print(haveFix ? "GPS FIX" : "GPS SEARCHING");
  tft.setTextColor(COL_DIM);
  tft.print("   SAT ");
  tft.print(gpsSatsText());
  tft.print("   HDOP ");
  tft.print(gpsHdopText());

  // Link freshness - always honest about it.
  bool everReceived = recordCount > 0;
  uint32_t ageS = everReceived ? (millis() - lastRecordMs) / 1000 : 0;
  if (!everReceived) {
    snprintf(buf, sizeof(buf), "NO HOST");
  } else {
    snprintf(buf, sizeof(buf), "%lus #%lu", (unsigned long)ageS, (unsigned long)recordCount);
  }
  int16_t linkW = (int16_t)(strlen(buf) * CHAR_W);
  putValue(PANEL_W - MARGIN - linkW, GPS_Y, linkW, CHAR_H, COL_BG,
           everReceived ? (ageS > 30 ? COL_WARN : COL_DIM) : COL_WARN, 1);
  tft.print(buf);

  // Session label, small, above the instruction.
  tft.fillRect(MARGIN, GPS_Y + 11, PANEL_W - 2 * MARGIN, CHAR_H, COL_BG);
  drawClipped(MARGIN, GPS_Y + 11, PANEL_W - 2 * MARGIN, fieldName, COL_DIM, 1);

  // THE INSTRUCTION. The largest thing on the panel, and the only thing an
  // operator reads while walking.
  tft.fillRect(MARGIN, ACTION_Y, PANEL_W - 2 * MARGIN, ACTION_H, COL_BG);
  uint16_t actionColour = COL_TEXT;
  if (!strcmp(workflowState, "ERROR"))              actionColour = COL_BAD;
  else if (!strcmp(workflowState, "MEASURING"))     actionColour = COL_ACCENT;
  else if (!strcmp(workflowState, "SAMPLE_SAVED"))  actionColour = COL_GOOD;
  else if (!strcmp(workflowState, "PROCESSING"))    actionColour = COL_ACCENT;
  drawCentered(MARGIN, ACTION_Y, PANEL_W - 2 * MARGIN, ACTION_H,
               actionLine, actionColour, 3);

  // Soil card values, two columns.
  int16_t vA = SOIL_COL_A + 64, vB = SOIL_COL_B + 22;
  putFloat(vA, SOIL_Y + 6,                  60, soilMoisture, 1, COL_TEXT);
  if (soilMoisture >= 0.0f) tft.print("%");
  putFloat(vA, SOIL_Y + 6 + SOIL_ROW_H,     60, soilPh,       2, COL_TEXT);
  putFloat(vA, SOIL_Y + 6 + SOIL_ROW_H * 2, 60, soilEc,       2, COL_TEXT);
  putInt(vB, SOIL_Y + 6,                    60, soilN, COL_TEXT);
  putInt(vB, SOIL_Y + 6 + SOIL_ROW_H,       60, soilP, COL_TEXT);
  putInt(vB, SOIL_Y + 6 + SOIL_ROW_H * 2,   60, soilK, COL_TEXT);

  // Stored samples, and how many of them are far enough apart to be separate
  // places. The second number is the honest denominator for any spatial claim,
  // so it gets its own value column rather than the shared one: "SITES" is five
  // characters where N/P/K are one, and at the shared offset the value box
  // clipped the label's last letter to "SITE" on the glass.
  putValue(vA, SOIL_Y + 6 + SOIL_ROW_H * 3, 60, CHAR_H, COL_CARD, COL_TEXT, 1);
  if (totalSamples < 0) {
    tft.print("--");
  } else {
    tft.print(totalSamples);
    if (validSamples >= 0) { tft.print(" OK "); tft.print(validSamples); }
  }
  putInt(SOIL_COL_B + 40, SOIL_Y + 6 + SOIL_ROW_H * 3, 42, distinctLocs, COL_TEXT);

  // Bottom bar. Shape follows the workflow; contents follow the state.
  bool wantButton = workflowArmed();
  if (!barShapeKnown || wantButton != barIsButton) {
    renderBarChrome(wantButton);
  }

  if (wantButton) {
    snprintf(buf, sizeof(buf), "PRESS START");
    drawCentered(MARGIN, BAR_Y, PANEL_W - 2 * MARGIN, BAR_H - 2, buf, COL_BG, 3);
  } else if (!strcmp(workflowState, "RESULT")) {
    tft.fillRect(MARGIN + 2, BAR_Y + 2, PANEL_W - 2 * MARGIN - 4, BAR_H - 6, COL_CARD);
    label(SOIL_COL_A, BAR_Y + 8, "FIELD STATUS", COL_DIM, 1);
    // Score bar, which is what reads from a distance.
    int16_t trackX = PANEL_W / 2 + 10, trackW = PANEL_W / 2 - 10 - MARGIN - 6;
    // The status is clipped to the space left of the score bar. Every status
    // this pipeline emits fits, but the host owns this string and a long one
    // would otherwise run under the bar rather than being cut short.
    drawClipped(SOIL_COL_A, BAR_Y + 22, trackX - SOIL_COL_A - 6,
                statusText, statusColour(), 2);
    tft.fillRect(trackX, BAR_Y + 26, trackW, 10, COL_BG);
    if (healthScore >= 0.0f) {
      int16_t fill = (int16_t)(trackW * healthScore);
      if (fill < 0) fill = 0;
      if (fill > trackW) fill = trackW;
      tft.fillRect(trackX, BAR_Y + 26, fill, 10, statusColour());
      putValue(trackX, BAR_Y + 8, trackW, CHAR_H, COL_CARD, COL_TEXT, 1);
      tft.print(healthScore, 2);
      tft.print("  Z");
      tft.print(zoneCount < 0 ? 0 : zoneCount);
      tft.print("  A");
      tft.print(recCount < 0 ? 0 : recCount);
    }
  } else {
    tft.fillRect(MARGIN + 2, BAR_Y + 2, PANEL_W - 2 * MARGIN - 4, BAR_H - 6, COL_CARD);
    // State token, plus the last sample's quality verdict when there is one.
    // READY_NEXT_SAMPLE is the longest state at 17 characters; the clip keeps
    // it off the quality label whatever the host sends.
    int16_t qualityW = (int16_t)(strlen(lastQuality) * CHAR_W);
    int16_t stateW = PANEL_W - MARGIN - 8 - qualityW - SOIL_COL_A - 6;
    drawClipped(SOIL_COL_A, BAR_Y + 10, stateW, workflowState, COL_ACCENT, 2);
    if (lastQuality[0]) {
      label(PANEL_W - MARGIN - 8 - qualityW, BAR_Y + 14, lastQuality,
            qualityColour(), 1);
    }
    if (offlineMode == 1) {
      label(SOIL_COL_A, BAR_Y + 34, "OFFLINE", COL_GOOD, 1);
    }
    if (!touchPresent) {
      // Say so on the glass. A unit whose touch is not answering must not
      // look identical to one where it is - the operator would keep pressing
      // a target that does nothing instead of reaching for the board keys.
      const char *note = "NO TOUCH";
      label(PANEL_W - MARGIN - 8 - (int16_t)(strlen(note) * CHAR_W),
            BAR_Y + 34, note, COL_WARN, 1);
    }
  }
}


// ------------------------------------------------------------- lifecycle

void setup() {
  pinMode(TFT_LED, OUTPUT);
  digitalWrite(TFT_LED, HIGH);
  delay(500);
  SPI.begin();

  // Native 240x320 glass, driven as a 320x240 landscape surface. Every
  // coordinate in this file is written against the rotated surface.
  tft.init(240, 320);
  tft.setRotation(PANEL_ROTATION);
  tft.invertDisplay(false);

  Bridge.begin();
  Monitor.begin(115200);

  renderChrome();
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

  // Values only - the chrome is already on the glass, and redrawing it is what
  // caused the black wipe.
  static uint32_t lastPaint = 0;
  if (dirty || millis() - lastPaint > 1000) {
    dirty = false;
    lastPaint = millis();
    renderValues();
  }
}
