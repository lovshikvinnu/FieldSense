// FieldSense AI - unified UNO Q firmware: MCU-rendered dashboard + NEO-M8N GPS.
//
// This is the sketch the assembled unit runs. It is dashboard.ino verbatim,
// plus the GPS receiver that used to live in its own sketch. They had to
// merge: only one sketch can be on the MCU at a time, so as long as the
// display and the GPS stayed in separate .ino files the assembled system
// could only ever have one of them.
//
// The soil probe is deliberately NOT here - see the UART ownership note below.
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

// NEVER call fillScreen() on a periodic repaint.
//
// render() used to clear the whole panel and redraw it once a second. There is
// no framebuffer between this sketch and the ST7789 - every draw lands on glass
// immediately - so the clear is visible: 153,600 bytes at the library default
// 24 MHz is ~51 ms of blank panel, followed by the elements reappearing one at
// a time. Physically that reads as a black wipe sweeping the dashboard once per
// second, which is what was observed on hardware.
//
// The split below is the whole fix. Coordinates, colours, fonts, card geometry
// and the record format are unchanged - only WHEN pixels are written.

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
  // Link state - always honest about freshness.
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

  // Field name
  putValue(14, 48, PANEL_W - 28, 8, COL_CARD, COL_TEXT, 1);
  tft.print(fieldName);

  // Headline status
  putValue(14, 96, PANEL_W - 28, 16, COL_CARD, statusColour(), 2);
  tft.print(statusText);

  // Score as a number plus a bar - the bar is what reads from a distance.
  putValue(150, 146, 70, 8, COL_CARD, COL_TEXT, 1);
  if (healthScore < 0.0f) {
    tft.print("--");
  } else {
    tft.print(healthScore, 2);
  }
  // Always clear the full track first or a shrinking score would leave the
  // tail of the previous bar behind it.
  tft.fillRect(14, 160, PANEL_W - 40, 8, COL_BG);
  if (healthScore >= 0.0f) {
    int16_t barW = (int16_t)((PANEL_W - 40) * healthScore);
    if (barW < 0) barW = 0;
    if (barW > PANEL_W - 40) barW = PANEL_W - 40;
    tft.fillRect(14, 160, barW, 8, statusColour());
  }

  // Sample counts
  putCount(198, totalSamples,    COL_TEXT);
  putCount(212, validSamples,    COL_GOOD);
  putCount(226, rejectedSamples, rejectedSamples > 0 ? COL_WARN : COL_DIM);
  putCount(240, zoneCount,       COL_TEXT);
  putCount(254, recCount,        COL_ACCENT);

  // Provenance footer. Evidence level and offline flag matter for trust, so
  // they get their own line rather than being buried.
  putValue(90, 292, PANEL_W - 104, 8, COL_CARD, COL_TEXT, 1);
  tft.print(evidence);
  putValue(14, 302, PANEL_W - 28, 8, COL_BG,
           offlineMode == 1 ? COL_GOOD : COL_BG, 1);
  if (offlineMode == 1) {
    tft.print("OFFLINE MODE");
  }
}

// ----------------------------------------------------------------- GPS

// NEO-M8N on Serial1 (D0/D1), the board's only exposed hardware UART.
//
// UART OWNERSHIP - READ BEFORE ADDING A PERIPHERAL
//
// Serial1 belongs to the GPS and to nothing else. The MAX485 soil transceiver
// also speaks UART and its bench sketch claimed this very port; the two were
// validated on separate flashes and would have fought over D0/D1 the moment
// they shared a board. In the assembled unit the probe hangs off the Linux
// side instead, on a USB-RS485 dongle at /dev/ttyUSB0, selected with
// FIELDSENSE_SOURCE=HARDWARE. Do NOT add a Modbus master here: there is no
// second header UART to move the GPS to.
//
// Reads are NON-BLOCKING, which the bench sketch's readStringUntil('\n') was
// not. That call blocks until a newline or the Stream timeout - a second by
// default - and this loop cannot afford it, because the same loop also
// services a 153,600 byte frame transfer. One byte at a time, accumulated
// into a line, is the only shape that lets the panel and the GPS share a
// single loop().
//
// NMEA sentences ARE dropped while a frame streams: Serial1's RX buffer is
// far smaller than a one-second burst. That is a deliberate trade. The fix
// only has to be current when a sample is taken, samples are taken between
// frames, and dropping a sentence costs a stale position where blocking
// would cost a sheared image.

#include <stdio.h>    // snprintf, for the GPS diagnostic string
#include <string.h>   // strncmp, for the sentence-type check below

#define GPS_SERIAL Serial1

static const uint32_t GPS_BAUD     = 9600;   // NEO-M8N factory default, 8N1
static const size_t   GPS_LINE_MAX = 120;    // longest GGA observed is ~82
static const uint32_t GPS_DRAIN_MS  = 400;   // tight-poll window per loop pass

static char   gpsLine[GPS_LINE_MAX];
static size_t gpsLineLen = 0;

// Diagnostics for a receiver that never produces a fix. Linux cannot observe
// Serial1 - it is physically on the MCU - so without these counters a silent
// GPS and a GPS whose sentences are all being rejected look identical from
// the host. They ride along on the NO_FIX string, which parse_gps_telemetry()
// short-circuits on parts[0], so extra trailing fields are ignored by the
// contract and cost nothing.
static uint32_t gpsBytes     = 0;   // raw bytes seen on the UART
static uint32_t gpsLines     = 0;   // complete newline-terminated lines
static uint32_t gpsChecksumOk = 0;  // lines whose NMEA checksum validated
static uint32_t gpsGgaSeen   = 0;   // GGA sentences handed to parseGGA
static bool     gpsEverParsed = false;
static bool     gpsDiscarding = false;  // dropping through to the next newline
static uint32_t gpsOverflows  = 0;      // merged/overlong lines discarded
static char     gpsLastLine[48];    // first 47 chars of the most recent line

// The wire contract with the host. Fixed by parse_gps_telemetry() in
// fieldsense/hardware/gps/bridge_gps.py:
//     FIX_OK,DDMM.MMMMN,DDDMM.MMMME,Sats:NN,HDOP:N.NN
//     NO_FIX,...
// Changing the shape of this string breaks the host parser silently.
static String latest_gps_csv = "NO_FIX,0.0,0.0,Sats:0,HDOP:99.9";

static int gpsHexVal(char c) {
  if (c >= '0' && c <= '9') { return c - '0'; }
  if (c >= 'A' && c <= 'F') { return c - 'A' + 10; }
  if (c >= 'a' && c <= 'f') { return c - 'a' + 10; }
  return -1;
}

// Verify the NMEA XOR checksum over everything between '$' and '*'.
//
// The bench sketch skipped this entirely. A sentence corrupted in transit
// whose comma structure happens to survive still parses into a plausible
// latitude, and the host has no way to tell it from a real fix - the
// checksum is the only place that can catch it.
static bool nmeaChecksumValid(const char *s, size_t len) {
  if (len < 4 || s[0] != '$') {
    return false;
  }
  size_t star = 0;
  bool haveStar = false;
  for (size_t i = len; i > 0; i--) {
    if (s[i - 1] == '*') { star = i - 1; haveStar = true; break; }
  }
  if (!haveStar || star + 2 >= len) {
    return false;
  }
  uint8_t sum = 0;
  for (size_t i = 1; i < star; i++) {
    sum ^= (uint8_t)s[i];
  }
  int hi = gpsHexVal(s[star + 1]);
  int lo = gpsHexVal(s[star + 2]);
  if (hi < 0 || lo < 0) {
    return false;
  }
  return sum == (uint8_t)((hi << 4) | lo);
}

static String gpsField(const char *s, int from, int to) {
  String out;
  for (int i = from; i < to; i++) {
    out += s[i];
  }
  return out;
}

// GGA field indices: 2=lat 3=N/S 4=lon 5=E/W 6=fix quality 7=sats 8=HDOP.
//
// Reaching field 8 requires comma index 8, so NINE commas must have been
// seen. The bench sketch guarded on `commaCount >= 8` and then read
// indices[8] - one past the last slot it had filled. On a truncated sentence
// that is uninitialised stack, and substring() ran to a garbage offset.
static void parseGGA(const char *s, size_t len) {
  int idx[16];
  int commas = 0;
  for (size_t i = 0; i < len && commas < 16; i++) {
    if (s[i] == ',') { idx[commas++] = (int)i; }
  }
  if (commas < 9) {
    return;
  }

  String lat    = gpsField(s, idx[1] + 1, idx[2]);
  String latDir = gpsField(s, idx[2] + 1, idx[3]);
  String lon    = gpsField(s, idx[3] + 1, idx[4]);
  String lonDir = gpsField(s, idx[4] + 1, idx[5]);
  String fix    = gpsField(s, idx[5] + 1, idx[6]);
  String sats   = gpsField(s, idx[6] + 1, idx[7]);
  String hdop   = gpsField(s, idx[7] + 1, idx[8]);

  // Fix quality 0 means the receiver has no usable solution yet. Say NO_FIX
  // rather than forwarding the empty coordinate fields: the host would read
  // 0.0,0.0 as a real position in the Gulf of Guinea.
  if (fix.length() == 0 || fix == "0" || lat.length() == 0 || lon.length() == 0) {
    // Keep the counters visible while there is no fix. Parsing health and
    // satellite lock are separate things: the first is verifiable indoors in
    // seconds, the second needs sky and can take minutes. Dropping the counters
    // the moment a sentence parsed would remove the only evidence that the
    // firmware works, exactly when someone is trying to confirm it - they would
    // wait for csum>0 and never see it, because success had erased it.
    //
    // Real Sats/HDOP here instead of the cold-start 0/99.9 is itself the proof:
    // those numbers can only come from a decoded sentence.
    char buf[176];
    snprintf(buf, sizeof(buf),
             "NO_FIX,0.0,0.0,Sats:%s,HDOP:%s,rx=%lu,lines=%lu,csum=%lu,gga=%lu,ovf=%lu",
             sats.c_str(), hdop.c_str(),
             (unsigned long)gpsBytes, (unsigned long)gpsLines,
             (unsigned long)gpsChecksumOk, (unsigned long)gpsGgaSeen,
             (unsigned long)gpsOverflows);
    latest_gps_csv = String(buf);
    return;
  }

  // A fix is the end of diagnostics: the payload is the position and nothing
  // else, which is what parse_gps_telemetry() on the host wants to see.

  latest_gps_csv = "FIX_OK," + lat + latDir + "," + lon + lonDir +
                   ",Sats:" + sats + ",HDOP:" + hdop;
}

// Drain whatever Serial1 has buffered without ever waiting for more. Safe to
// call from anywhere in loop(), including between frame chunks.
// Rebuild the NO_FIX payload with live counters, so `arduino-app-cli app logs`
// shows where the pipeline breaks without another reflash:
//   rx=0                  nothing on the wire at all - wiring, power, or a
//                         second driver fighting the GPS on D0
//   rx>0 lines=0          bytes arriving but no newlines - wrong baud
//   lines>0 csum=0        sentences arriving but corrupt - baud or contention
//   csum>0 gga=0          valid NMEA, but no GGA - receiver configured off
static void publishNoFix() {
  char buf[160];
  snprintf(buf, sizeof(buf),
           "NO_FIX,0.0,0.0,Sats:0,HDOP:99.9,rx=%lu,lines=%lu,csum=%lu,gga=%lu,ovf=%lu,last=%s",
           (unsigned long)gpsBytes, (unsigned long)gpsLines,
           (unsigned long)gpsChecksumOk, (unsigned long)gpsGgaSeen,
           (unsigned long)gpsOverflows, gpsLastLine);
  latest_gps_csv = String(buf);
}

// Send one PUBX sentence with a computed checksum.
//
// WHY THE RECEIVER MUST BE QUIETENED
//
// A NEO-M8N ships talking GGA, GLL, GSA, GSV, RMC and VTG - roughly 960 bytes
// every second at 9600 baud. This loop drains the UART about 1.7 times a
// second, because Serial.available() on the Monitor transport costs ~595 ms a
// call. The receive buffer is a few dozen bytes and cannot bridge that gap, so
// characters vanish from the middle of sentences and EVERY checksum fails.
// Measured on hardware: rx=275, lines=4, csum=0.
//
// Dropping every sentence but GGA takes the load to ~70 bytes per second,
// which one buffer-full comfortably holds between drains. GGA alone carries
// fix, latitude, longitude, satellites and HDOP - everything parseGGA reads.
//
// These settings live in RAM on the receiver, so they are re-sent every boot.
static void sendPubx(const char *body) {
  uint8_t sum = 0;
  for (const char *p = body; *p; p++) {
    sum ^= (uint8_t)*p;
  }
  char frame[48];
  snprintf(frame, sizeof(frame), "$%s*%02X\r\n", body, sum);
  GPS_SERIAL.print(frame);
  GPS_SERIAL.flush();
}

static void quietenGPS() {
  static const char *OFF[] = {
    "PUBX,40,GLL,0,0,0,0,0,0",
    "PUBX,40,GSA,0,0,0,0,0,0",
    "PUBX,40,GSV,0,0,0,0,0,0",
    "PUBX,40,RMC,0,0,0,0,0,0",
    "PUBX,40,VTG,0,0,0,0,0,0",
    "PUBX,40,ZDA,0,0,0,0,0,0",
  };
  for (size_t i = 0; i < sizeof(OFF) / sizeof(OFF[0]); i++) {
    sendPubx(OFF[i]);
    delay(20);
  }
  sendPubx("PUBX,40,GGA,1,1,1,1,0,0");   // GGA on, every fix
  delay(20);
}

static void serviceGPS() {
  while (GPS_SERIAL.available() > 0) {
    char c = (char)GPS_SERIAL.read();
    gpsBytes++;

    if (c == '\n' || c == '\r') {
      gpsDiscarding = false;
      if (gpsLineLen > 0) {
        gpsLine[gpsLineLen] = '\0';
        gpsLines++;

        // Keep a sanitised echo of the last line. Commas would split the CSV
        // the host parses, so they become ';'.
        size_t copy = gpsLineLen < sizeof(gpsLastLine) - 1
                        ? gpsLineLen : sizeof(gpsLastLine) - 1;
        for (size_t i = 0; i < copy; i++) {
          char ch = gpsLine[i];
          // Printable ASCII only. A dropped-character line carries arbitrary
          // bytes, and one 0x9b travelling up the Bridge breaks its UTF-8
          // decode and kills the RPC channel for every method, not just this
          // one. Commas become ';' so they cannot split the host's CSV.
          if (ch == ',') {
            gpsLastLine[i] = ';';
          } else if (ch >= 0x20 && ch <= 0x7E) {
            gpsLastLine[i] = ch;
          } else {
            gpsLastLine[i] = '.';
          }
        }
        gpsLastLine[copy] = '\0';

        if (nmeaChecksumValid(gpsLine, gpsLineLen)) {
          gpsChecksumOk++;
          if (strncmp(gpsLine, "$GNGGA", 6) == 0 ||
              strncmp(gpsLine, "$GPGGA", 6) == 0) {
            gpsGgaSeen++;
            gpsEverParsed = true;
            parseGGA(gpsLine, gpsLineLen);
            gpsLineLen = 0;
            continue;
          }
        }
        if (!gpsEverParsed) {
          publishNoFix();
        }
        gpsLineLen = 0;
      }
      continue;
    }

    if (gpsDiscarding) {
      continue;  // mid-overflow: throw bytes away until the next newline
    }
    if (gpsLineLen < GPS_LINE_MAX - 1) {
      gpsLine[gpsLineLen++] = c;
    } else {
      // Two sentences merged because a newline was lost. Resetting the length
      // and carrying on would hand parseGGA the tail of one sentence as if it
      // were a whole one; discard through to the next newline instead.
      gpsLineLen = 0;
      gpsDiscarding = true;
      gpsOverflows++;
    }
  }
}

// Bridge endpoint the Linux side calls. Defined above setup() rather than
// relying on the .ino auto-prototyper, which does not always handle a String
// return type cleanly.
String get_gps_data() {
  return latest_gps_csv;
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

  // GPS after the bridge: provide() needs a live RPC transport under it.
  // Serial1 is a real UART and is entirely independent of Serial, which on
  // this board is the RouterBridge Monitor - the two never contend.
  GPS_SERIAL.begin(GPS_BAUD);
  delay(100);      // let the UART settle before configuring the receiver
  quietenGPS();
  Bridge.provide("get_gps_data", get_gps_data);

  renderChrome();
  renderValues();
}

void loop() {
  // Drain Serial1 continuously for a while BEFORE paying for one Monitor
  // available().
  //
  // A single serviceGPS() per pass is not enough and the hardware said so:
  // rx=1518 with lines=2, because Serial.available() costs ~595 ms and the
  // receive buffer cannot hold that much GPS traffic. Bytes vanished, newlines
  // among them, sentences merged, and every checksum failed.
  //
  // Polling every 2 ms admits only a byte or two between reads, so the buffer
  // never approaches full. The cost is panel latency, which is free here: the
  // dashboard repaints on new data or once a second, whichever comes first,
  // and a record is ~76 bytes that can wait 400 ms.
  uint32_t drainUntil = millis() + GPS_DRAIN_MS;
  while ((int32_t)(millis() - drainUntil) < 0) {
    serviceGPS();
    delay(2);
  }

  // available() costs ~595 ms on this transport, so one call per pass and take
  // everything it offers. Never poll it in a tight inner loop.
  int avail = Serial.available();
  while (avail > 0) {
    int c = Serial.read();
    if (c < 0) break;
    avail--;

    // Drain Serial1 between panel bytes as well. Cheap - it touches a real
    // UART, not the RPC transport - and it narrows the window in which the
    // receive buffer can overflow.
    serviceGPS();

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
  // caused the black wipe. Once a second is enough for the age counter, and
  // this now costs a few hundred bytes of SPI instead of 153,600.
  static uint32_t lastPaint = 0;
  if (dirty || millis() - lastPaint > 1000) {
    dirty = false;
    lastPaint = millis();
    renderValues();
  }
}
