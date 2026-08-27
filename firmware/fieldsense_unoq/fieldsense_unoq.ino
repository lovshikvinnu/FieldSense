// FieldSense AI - unified UNO Q firmware: landscape field panel + NEO-M8N GPS
// + the operator's START control.
//
// This is the sketch the assembled field unit runs. It carries three things
// that cannot live in separate sketches, because only one sketch can be on the
// MCU at a time:
//
//   1. the 320x240 LANDSCAPE field panel,
//   2. the NEO-M8N GPS receiver and its Bridge endpoint,
//   3. the START control the operator uses to say "this is sample N".
//
// The soil probe is deliberately NOT here - see the UART ownership note below.
//
// WHY LANDSCAPE
//
// The panel used to render portrait, 240 wide by 320 tall, because that is the
// ST7789's native orientation and the first dashboard was a column of stat
// rows. That shape is wrong for this instrument. The two things an operator
// reads while standing over a probe are one short instruction and one sample
// counter, and both are horizontal: 240 px of width forces the instruction to
// text size 1 or to wrap, while 320 px fits "MOVE TO NEXT LOCATION" at size 2
// and "SAMPLE 1 SAVED" at size 3.
//
// This is a re-layout, not a rotation. setRotation(1) alone would have left
// every coordinate below computed against a 240-wide screen, so the stat
// column would have hugged the left third and the footer would have sat 80 px
// above the bottom edge. Every coordinate here is computed against
// PANEL_W = 320, PANEL_H = 240.
//
// WHY THIS RECEIVES VALUES AND NOT PIXELS
//
// frame_receiver.ino ships a full RGB565 frame - 153,600 bytes - from the
// QRB2210 to this MCU. On the UNO Q that cannot work, and the numbers say so
// rather than any hunch:
//
//   * Serial here is Arduino_RouterBridge's Monitor, and every
//     Serial.available() costs ~595 ms whether or not data is waiting - it is
//     a mon/read RPC round trip, measured at 1.68 calls/second by
//     link_probe.ino over a 247-second run.
//   * That caps the link at roughly 512 bytes per 595 ms, about 860 B/s.
//     A single frame would take three minutes.
//
// So this sketch receives VALUES - one short newline-terminated record - and
// draws the panel itself with Adafruit_GFX. The full workflow record is about
// 135 bytes, well under a second even at the measured rate, and the panel
// stays readable when nothing arrives at all.
//
// RECORD FORMAT, newline-terminated, order-independent, unknown keys ignored:
//
//   FS|t=READY|i=2|m=5|a=MOVE TO NEXT LOCATION|w=31.2|p=6.60|k=0.42|o=1
//   FS|f=North Paddock|s=HEALTHY|h=0.79|n=5|v=5|r=0|z=2|c=4|e=LIMITED|o=1
//
//     f  field / session name  (text)
//     s  soil health status    (text, drives the status colour)
//     h  soil health score     (0..1)
//     n  stored samples        v  valid samples      r  flagged samples
//     z  zone count            c  recommendation count
//     e  evidence level        (text)
//     o  offline mode          (1/0)
//     t  workflow state        BOOT|READY|MEASURING|SAMPLE_SAVED|
//                              READY_NEXT_SAMPLE|PROCESSING|RESULT|ERROR
//     i  current sample index  m  planned sample count
//     a  operator instruction  (text, drawn at the largest size that fits)
//     q  last sample quality   VALID|SUSPICIOUS|RETRY|REJECTED
//     d  distinct locations    (fixes clear of the GPS noise floor)
//     w  moisture %            p  pH        k  EC
//     x  nitrogen              y  phosphorus  j  potassium
//
// Values persist until replaced, so a dropped update leaves the last good
// reading on screen rather than blanking it. The header always shows link
// state and seconds since the last accepted record, so the panel never lies
// about how fresh it is.
//
// THE OPERATOR CONTROL
//
// The workflow needs an explicit "this measurement is sample N" from a person.
// It must not be inferred from GPS movement: a stationary receiver drifts
// several metres, and a previous bench run produced five distinct coordinates
// spanning 8 m at HDOP 3.58 - one physical location wearing five hats.
//
// The control serviced here is the XPT2046 laminated to this same panel, on
// TOUCH_CS with its own SPI transaction at 2 MHz. Presence is probed at boot
// rather than assumed, and the probe result rides out on the GPS telemetry line
// so Linux can see whether touch is answering without anyone opening the
// enclosure.
//
// It is not the only operator control, and deliberately not the primary one.
// The board's own USER button is read on the Linux side straight from the
// kernel's gpio-keys evdev node - soldered on, nothing to wire, and no RPC
// round trip. (The kernel labels that line "Volume Up/Down", inherited from
// the Qualcomm SoM reference device tree; the UNO Q has no volume keys.) This panel target is the second path, so a unit whose touch is
// unwired is still fully operable.
//
// The touch target is the bottom bar and only the bottom bar. The integration
// record for this panel documents a mechanical lamination pinch that produces
// phantom Z-axis touches NEAR THE CENTRE of the glass, so the centre is not a
// safe place to put a control; the bottom bar's centre is ~95 px clear of it.
// A press must also be held for TOUCH_HOLD_MS, which phantom contacts do not
// survive.
//
// Presses are reported to Linux as a MONOTONIC COUNTER appended to the GPS
// telemetry string, never as a level or an edge. The host polls at about 1 Hz
// and a press lasts a few hundred milliseconds, so a level would be missed
// about as often as it was caught. A counter cannot miss one: the host
// compares against the value it saw last.

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
// Rotation 3, not 1: the same landscape surface turned through 180 degrees, so
// the unit reads correctly in the orientation it is actually held. Both values
// are landscape and both report 320x240, so every coordinate in this file maps
// unchanged - the driver rewrites MADCTL and the whole image turns together.
// Anything other than 1 or 3 here would be portrait and would invalidate the
// entire layout.
static const uint8_t  PANEL_ROTATION = 3;

// Adafruit_GFX's built-in font is 6x8 px per character at size 1 and scales by
// integer multiples. Named here because every fit calculation below uses them.
static const uint8_t  CHAR_W = 6;
static const uint8_t  CHAR_H = 8;

// Deep slate, matching the dashboard HTML so the panel and the browser view
// read as the same product rather than two different tools.
// Black, explicitly. This was a deep slate (0x0861) borrowed from the HTML
// dashboard, which is nearly black on a monitor and visibly grey on this panel
// in daylight - and any region cleared to it read as a grey flash rather than
// as background. Every clear in this file uses COL_BG, so this one constant is
// the whole of "the panel initialises to black and stays black".
static const uint16_t COL_BG     = 0x0000;
static const uint16_t COL_CARD   = 0x18E3;
static const uint16_t COL_TEXT   = ST77XX_WHITE;
static const uint16_t COL_DIM    = 0x8410;
// Traffic-light palette, RGB565 of the specified sRGB values. Pure 0x07E0
// green and 0xF800 red were the driver's primaries, not design choices - they
// read as neon indoors and wash out in sunlight. These are the Material tones
// the rest of the product uses.
static const uint16_t COL_GOOD   = 0x072E;   // #00E676 optimal / valid / ready
static const uint16_t COL_GOOD_D = 0x4D6A;   // #4CAF50 dimmer green, for fills
static const uint16_t COL_WARN   = 0xFCC0;   // #FF9800 moderate / re-seat / jitter
static const uint16_t COL_WARN_D = 0xFD80;   // #FFB300
static const uint16_t COL_BAD    = 0xFA8A;   // #FF5252 poor / air probe / error
static const uint16_t COL_BAD_D  = 0xF206;   // #F44336
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
static const int16_t HEADER_Y   = 0,   HEADER_H = 30;
static const int16_t PROG_Y     = 33,  PROG_H   = 13;
static const int16_t GPS_Y      = 49,  GPS_H    = 16;
static const int16_t ACTION_Y   = 68,  ACTION_H = 48;
static const int16_t SOIL_Y     = 120, SOIL_H   = 58;
static const int16_t BAR_Y      = 182, BAR_H    = 58;
static const int16_t MARGIN     = 6;

// Two columns inside the soil card, and four label/value rows in each.
static const int16_t SOIL_COL_A = MARGIN + 8;
static const int16_t SOIL_COL_B = PANEL_W / 2 + 6;
static const int16_t SOIL_ROW_H = 13;

// One tile per planned sample, drawn across PROG_Y. Width is computed from the
// count the host sends rather than fixed at five, so changing SAMPLES does not
// silently leave the strip wrong.
static const int16_t PROG_GAP   = 4;

// ------------------------------------------------------------- panel state

static char     fieldName[24]   = "FieldSense";
static char     statusText[16]  = "NO DATA";
static char     evidence[16]    = "-";
static char     workflowState[20] = "BOOT";
static char     actionLine[40]  = "STARTING";
static char     lastQuality[14] = "";
static char     buttonLabel[20]  = "";   // empty means the device is busy
static char     progressSegments[12] = "";  // one char per planned sample
static char     zoneStatuses[12] = "";   // one char per zone: G A R ?
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
  else if (!strcmp(key, "b")) copyField(buttonLabel, sizeof(buttonLabel), value);
  else if (!strcmp(key, "g")) copyField(progressSegments, sizeof(progressSegments), value);
  else if (!strcmp(key, "u")) copyField(zoneStatuses, sizeof(zoneStatuses), value);
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

// --------------------------------------------------------- operator control

// XPT2046, driven directly rather than through XPT2046_Touchscreen.
//
// The library would be a tenth dependency on a build whose nine libraries are
// pinned and verified offline-clean, and it would have to be fetched over a
// network this unit is supposed to run without. The controller itself is four
// single-shot ADC commands, which is the whole driver below.
//
// 2 MHz because the XPT2046's sample-and-hold needs the slower clock to settle;
// the display runs the same bus at 24 MHz. Both sides use SPI transactions, so
// the speeds do not collide.
static const uint32_t TOUCH_SPI_HZ  = 2000000;

// CONTROL BYTES USE PD = 00, NOT PD = 01.
//
// The low two bits are the power-down mode, and PD = 00 is the only setting
// that leaves PENIRQ enabled between conversions. The earlier 0xB1/0xC1 used
// PD = 01 - "reference off, ADC on" - which switches pen detection OFF the
// moment the first conversion is issued. That is self-defeating for an
// IRQ-gated driver: the first read would kill the very signal that decides when
// to read next, and touch would work exactly once.
//
//   0xB0  Z1     0xC0  Z2     0x90  Y     0xD0  X
static const uint8_t  CMD_Z1        = 0xB0;
static const uint8_t  CMD_Z2        = 0xC0;
static const uint8_t  CMD_Y         = 0x90;

//: Minimum gap between IRQ-gated SPI reads. Even while a finger is down, the
//: panel does not need sampling faster than this, and every sample is a
//: reconfiguration of a controller the display shares.
static const uint32_t TOUCH_SAMPLE_MS = 40;
static const uint16_t TOUCH_Z_MIN   = 400;   // below this is noise or no contact
static const uint16_t TOUCH_Z_MAX   = 4000;  // above this is a rail, not a finger
static const uint32_t TOUCH_HOLD_MS = 180;   // deliberate press, not a phantom

// A longer hold for the one action that throws something away.
//
// Touch on this unit has no coordinates - the loopback test proved SPI2 cannot
// receive (TX AA55 -> RX 0000, 194 runs, MOSI jumpered straight to MISO), so
// there is no hitbox and any contact anywhere is the current action. For START,
// NEXT and RETRY that is harmless: the worst case is a sample the operator
// immediately retakes.
//
// RESULT is different. There the action is NEW RUN, and a stray brush dismisses
// a field result the operator may not have read yet - which is exactly what was
// reported, a centre touch firing NEW RUN. Nothing is lost from disk (the
// session is written and closed before the result is shown), but the screen is.
//
// This is not an arbitrary delay. It is the only defence available once
// position is unavailable, it is scoped to the single destructive action, and
// it is proportionate to that action rather than applied to every press.
static const uint32_t RESULT_HOLD_MS = 1200;
static const uint32_t PRESS_LOCKOUT_MS = 1200;  // one press per press

static bool     touchPresent   = false;
// True once the controller has answered an SPI read with anything non-zero.
// Separate from touchPresent, because on this unit the panel detects touch
// (PENIRQ) while the SPI side stays silent - two different facts that were
// previously conflated into one flag.
static bool     spiAnswering   = false;
static uint16_t lastTouchZ     = 0;
// Raw ADC from both pressure channels, refreshed every pass whether or not the
// boot probe found a controller.
//
// Reporting only the derived pressure was not enough to diagnose a panel that
// reports TP:0. Derived pressure is zero for "no controller", for "controller
// present, nothing touching it", and for "MISO stuck at a rail" - three
// different faults that need three different fixes. The raw pair separates
// them: 0/0 is a dead or unwired MISO, 4095/4095 is a floating one, and a
// small z1 with a large z2 is a healthy untouched controller whose presence
// heuristic is what needs adjusting.
static uint16_t lastTouchZ1    = 0;
static uint16_t lastTouchZ2    = 0;
// Where the last contact landed, in panel Y. Reported so the axis calibration
// can be checked from Linux with one touch instead of a flash-and-look cycle:
// if a press on the bottom bar reports a small TY, the axis is inverted for
// this panel and the map() in contactInBar() needs its ends swapped.
static int16_t  lastTouchY     = -1;
// PENIRQ state, sampled with digitalRead and NOTHING ELSE.
//
// This is the one touch measurement that costs no SPI, and it is therefore the
// only one that can run while TOUCH_ENABLED is 0 - which matters, because
// polling the bus is what whitened the panel.
//
// The XPT2046's PENIRQ is an open-drain output, active LOW on pen-down, and it
// is ENABLED BY DEFAULT: the chip powers up with PD1:PD0 = 00, and only a
// conversion issued with PD != 00 disables it. With touch compiled out no
// conversion is ever issued, so the chip is sitting in exactly the state where
// PENIRQ works.
//
// That makes this decisive for the audit, in a way the SPI reads were not:
//
//   IL goes 1 when touched  -> the controller is POWERED and its IRQ line is
//                              wired. A zero SPI read is then a SPI wiring or
//                              protocol fault, not a dead chip.
//   IL stays 0 forever      -> nothing is pulling the line down. The controller
//                              is unpowered, absent, or IRQ is not connected -
//                              and no amount of SPI work will fix that.
//
// IQ is the instantaneous level; IL latches whether it has EVER read low, so a
// touch does not have to coincide with the host's ~1 Hz poll to be seen.
static bool     irqEverLow     = false;
static uint8_t  irqLevel       = 1;

static void serviceTouchIrq() {
  irqLevel = (uint8_t)digitalRead(TOUCH_IRQ);
  if (irqLevel == LOW) {
    irqEverLow = true;
  }
}

static uint32_t pressCount     = 0;    // monotonic; the host diffs it
static uint32_t lastPressMs    = 0;
static uint32_t contactBeganMs = 0;
static bool     contactActive  = false;

static uint16_t readTouchChannel(uint8_t command) {
  SPI.beginTransaction(SPISettings(TOUCH_SPI_HZ, MSBFIRST, SPI_MODE0));
  digitalWrite(TOUCH_CS, LOW);
  SPI.transfer(command);
  uint8_t hi = SPI.transfer(0x00);
  uint8_t lo = SPI.transfer(0x00);
  digitalWrite(TOUCH_CS, HIGH);
  SPI.endTransaction();
  // 12-bit result, left-aligned in the 16 bits that follow the command byte.
  return (uint16_t)(((hi << 8) | lo) >> 3);
}

// Contact pressure, the standard XPT2046 formula. Larger means harder.
static uint16_t readTouchZ() {
  uint16_t z1 = readTouchChannel(CMD_Z1);
  uint16_t z2 = readTouchChannel(CMD_Z2);
  lastTouchZ1 = z1;
  lastTouchZ2 = z2;
  if (z2 <= z1) {
    return 0;
  }
  return (uint16_t)(z1 + 4095 - z2);
}

// Decide whether a touch controller is actually wired, instead of assuming it.
//
// An absent chip leaves MISO floating, so both channels read the same rail -
// all zeros or all ones. A present, untouched XPT2046 reads z1 near the bottom
// of its range and z2 near the top, and that difference is the signature this
// looks for. The raw numbers ride out on the telemetry line either way, so if
// this heuristic is ever wrong on a particular unit it can be seen from Linux
// rather than guessed at.
static void probeTouch() {
  // Deselect the controller regardless, so a wired-but-unused XPT2046 cannot
  // sit with its chip select floating and drive the shared MISO line.
  pinMode(TOUCH_CS, OUTPUT);
  digitalWrite(TOUCH_CS, HIGH);
  pinMode(TOUCH_IRQ, INPUT_PULLUP);

  // NO SPI PROBE AT BOOT.
  //
  // The old probe clocked the controller six times during setup() to guess
  // whether it existed. That guess is now unnecessary and was never reliable:
  // presence is established by PENIRQ going low under a real finger and the
  // controller answering that read, which is direct evidence rather than an
  // inference from an untouched panel's idle levels. Leaving it out also keeps
  // setup() free of bus traffic that competes with the display's first paint.
  touchPresent = false;
}

// Is the contact inside the bottom bar?
//
// Only the Y axis is tested. The bar spans the full width, so X carries no
// information about whether the press was intended, and the raw-to-pixel X
// calibration is the axis most disturbed by the lamination pinch documented
// for this panel. Testing an axis that cannot change the answer would only add
// a way to reject a real press.
static bool contactInBar() {
  SPI.beginTransaction(SPISettings(TOUCH_SPI_HZ, MSBFIRST, SPI_MODE0));
  digitalWrite(TOUCH_CS, LOW);
  SPI.transfer(CMD_Y);                // Y channel, differential, PD=00
  uint8_t hi = SPI.transfer(0x00);
  uint8_t lo = SPI.transfer(0x00);
  digitalWrite(TOUCH_CS, HIGH);
  SPI.endTransaction();
  uint16_t raw = (uint16_t)(((hi << 8) | lo) >> 3);

  // Calibration from the bring-up sketch: raw 200..3700 spans the axis. In
  // rotation 1 that axis runs bottom-to-top; rotation 3 turns the panel through
  // 180 degrees, so it runs top-to-bottom and the map ends swap with it.
  // Untestable on this unit - the controller pen-detects but does not answer
  // over SPI, so contactInBar() never decides a press here - but it has to
  // follow the rotation or it would be silently wrong the day that wiring is
  // repaired.
  int32_t y = (PANEL_ROTATION == 3)
      ? (int32_t)map((int32_t)raw, 200, 3700, 0, (int32_t)PANEL_H)
      : (int32_t)map((int32_t)raw, 200, 3700, (int32_t)PANEL_H, 0);
  if (y < 0) y = 0;
  if (y > PANEL_H) y = PANEL_H;
  // Only report a landing position when the controller actually answered.
  // With SPI silent the raw read is 0, which map() turns into a confident-
  // looking 240 - a coordinate that is pure artifact. -1 says "unknown", which
  // is the truth, and keeps TY usable as evidence if the wiring is ever fixed.
  lastTouchY = spiAnswering ? (int16_t)y : (int16_t)-1;
  return y >= BAR_Y;
}

// Register a START press from whichever input produced it.
static void notePress() {
  uint32_t now = millis();
  if (now - lastPressMs < PRESS_LOCKOUT_MS) {
    return;   // contact bounce, or a finger resting on the glass
  }
  lastPressMs = now;
  pressCount++;
  dirty = true;
}

static void serviceOperatorInput() {
  if (!TOUCH_ENABLED) {
    return;   // the display owns the SPI bus; nothing else touches it
  }

  uint32_t now = millis();

  // THE GATE. No finger, no SPI - the whole reason the display survives this.
  // irqLevel is refreshed by serviceTouchIrq(), which is a bare digitalRead.
  if (irqLevel != LOW) {
    contactActive = false;
    return;
  }

  // Finger is down. Sample the bus, but not faster than necessary.
  static uint32_t lastSampleMs = 0;
  if (now - lastSampleMs < TOUCH_SAMPLE_MS) {
    return;
  }
  lastSampleMs = now;

  uint16_t z = readTouchZ();
  lastTouchZ = z;

  // Does this controller answer over SPI at all?
  //
  // On the assembled unit it does not. PENIRQ tracks a finger perfectly - that
  // circuit needs only VCC, GND and the panel itself - while every SPI read
  // returns zero, which places the fault on T_CS/T_CLK/T_DIN/T_DO. Firmware
  // cannot repair a wire.
  //
  // So the driver works from whichever signal it actually has. Coordinates are
  // used when the controller answers; pen-detect alone drives the workflow when
  // it does not. This is not a fallback bolted on to rescue a demo: every state
  // in this workflow offers EXACTLY ONE action - START, or NEXT, or RETRY, or
  // NEW RUN - so a press with no coordinate is unambiguous. Position buys
  // safety against stray contact, not capability.
  //
  // It also upgrades itself. The moment those four wires are fixed, a read
  // returns non-zero, spiAnswering latches true, and the hit-testing path below
  // takes over with no reflash.
  if (!spiAnswering && (lastTouchZ1 > 0 || lastTouchZ2 > 0)) {
    spiAnswering = true;
    dirty = true;
  }
  if (!touchPresent) {
    touchPresent = true;   // PENIRQ under a real finger is proof enough
    dirty = true;
  }

  // What counts as contact depends on which signal this unit actually has.
  //
  // Pressure is the better test when it is available: it rejects the rail
  // readings a floating input produces, and it scales with how hard the glass
  // was pressed. But keying on pressure UNCONDITIONALLY was a bug - on a unit
  // whose controller does not answer over SPI, z is permanently 0, so `contact`
  // was never true and notePress() was unreachable. PENIRQ fired, touchPresent
  // latched, and the press counter never moved: touch that looked alive in the
  // telemetry and did nothing at all.
  //
  // Reaching this line already means irqLevel == LOW - the gate above returned
  // otherwise - so pen-detect alone is a complete contact signal, and the only
  // honest one when the pressure channel is silent.
  bool contact = spiAnswering ? (z >= TOUCH_Z_MIN && z <= TOUCH_Z_MAX)
                              : (irqLevel == LOW);

  if (!contact) {
    contactActive = false;
    return;
  }
  if (!contactActive) {
    contactActive = true;
    contactBeganMs = now;
    contactInBar();      // for its side effect: record where this landed
    return;
  }
  // Held long enough to be deliberate.
  //
  // Two filters reject the phantom contacts this panel's lamination pinch
  // produces near the centre: a sustained hold, which brief phantoms do not
  // survive, and - only when the controller answers over SPI - a position
  // inside the bottom bar.
  //
  // With no coordinates available the hold and the press lockout are the whole
  // defence. That is weaker than hold-plus-position and is stated plainly
  // rather than papered over; it is also why TOUCH_HOLD_MS is not shortened to
  // make the panel feel snappier.
  // The result screen asks for a deliberate hold; everything else stays quick.
  uint32_t needHold = !strcmp(workflowState, "RESULT") ? RESULT_HOLD_MS
                                                       : TOUCH_HOLD_MS;
  if ((now - contactBeganMs) >= needHold) {
    if (!spiAnswering || contactInBar()) {
      notePress();
      contactActive = false;
    }
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

// Rolling window of the most recent raw bytes, and a count of how many bytes
// ever arrived with bit 7 set.
//
// WHY THE COUNTERS ARE NOT ENOUGH
//
// rx>0 with lines=0 says "bytes arrive, no line ever completes" but not WHY,
// and the two causes need opposite fixes: real NMEA at the wrong framing is a
// baud or contention problem, while noise on a floating pin is a wire that is
// not connected. gpsLastLine cannot separate them - it is only written when a
// line COMPLETES, which is exactly what is not happening.
//
// This window is filled in serviceGPS() before any line assembly, so it
// survives the overflow-discard path that is currently swallowing everything.
//
// hi is the decisive number, and it is one comparison against rx:
//   hi=0            every byte is 7-bit. This is ASCII text - so it IS NMEA,
//                   and the fault is framing: baud, or two drivers on the pin.
//   hi ~ rx/2       half the bytes have the high bit set. No ASCII protocol
//                   does that. The pin is floating and reading noise.
static const size_t GPS_RAW_WINDOW = 48;
static char     gpsRawWindow[GPS_RAW_WINDOW];
static size_t   gpsRawHead   = 0;   // next write position
static uint32_t gpsRawSeen   = 0;   // bytes ever written to the window
static uint32_t gpsHighBit   = 0;   // bytes arriving with bit 7 set

// millis() at the last parseGGA that published a position, and whether there
// has ever been one.
//
// latest_gps_csv PERSISTS until the next successful parse. On a healthy link
// that is invisible; on a degraded one the host can read a minutes-old
// position and staple it to a fresh soil sample, which is the exact failure
// this project keeps designing against - a value that reads like a
// measurement and is not. Nothing on the wire carried the fix's age, so the
// host had no way to tell a current position from a stale one.
//
// Unsigned subtraction, so the ~49.7-day millis() wrap is handled without a
// special case.
static uint32_t gpsLastFixMs = 0;
static bool     gpsHaveFix   = false;

// Render the window oldest-to-newest, safe to put on the wire.
//
// Two escapes, both mandatory rather than cosmetic. Commas would split the CSV
// the host parses. And a raw non-printable byte travelling up the Bridge breaks
// its UTF-8 decode and kills the RPC channel for EVERY method, not just this
// one - this project has already lost a debugging session to a stray 0x9b.
static void renderRawWindow(char *out, size_t outLen) {
  size_t n = gpsRawSeen < GPS_RAW_WINDOW ? (size_t)gpsRawSeen : GPS_RAW_WINDOW;
  size_t start = (gpsRawHead + GPS_RAW_WINDOW - n) % GPS_RAW_WINDOW;
  size_t w = 0;
  for (size_t i = 0; i < n && w + 1 < outLen; i++) {
    char ch = gpsRawWindow[(start + i) % GPS_RAW_WINDOW];
    if (ch == ',')                     { out[w++] = ';'; }
    else if (ch >= 0x20 && ch <= 0x7E) { out[w++] = ch;  }
    else                               { out[w++] = '.'; }
  }
  out[w] = '\0';
}

// Satellite count and HDOP as text, for the panel's GPS strip.
//
// The panel reads these rather than re-parsing latest_gps_csv. Two parsers for
// one sentence is two things to keep in step, and the host contract for that
// string is deliberately narrow - parse_gps_telemetry() reads four fields and
// ignores the rest, so anything the panel needs has to be kept here instead.
static char     gpsSats[8] = "--";
static char     gpsHdop[8] = "--";

const char *gpsSatsText() { return gpsSats; }
const char *gpsHdopText() { return gpsHdop; }

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
    snprintf(gpsSats, sizeof(gpsSats), "%s", sats.length() ? sats.c_str() : "--");
    snprintf(gpsHdop, sizeof(gpsHdop), "%s", hdop.length() ? hdop.c_str() : "--");
    char buf[224];
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

  snprintf(gpsSats, sizeof(gpsSats), "%s", sats.c_str());
  snprintf(gpsHdop, sizeof(gpsHdop), "%s", hdop.c_str());

  latest_gps_csv = "FIX_OK," + lat + latDir + "," + lon + lonDir +
                   ",Sats:" + sats + ",HDOP:" + hdop;
  gpsLastFixMs = millis();
  gpsHaveFix = true;
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

    // Before any line assembly: this has to see the bytes that the
    // overflow-discard path below throws away, because on a broken link those
    // are all of them.
    gpsRawWindow[gpsRawHead] = c;
    gpsRawHead = (gpsRawHead + 1) % GPS_RAW_WINDOW;
    if (gpsRawSeen < 0xFFFFFFFFul) { gpsRawSeen++; }
    if ((uint8_t)c & 0x80)         { gpsHighBit++; }

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
// Append the operator-control state to whatever the GPS currently reports.
//
// WHY THIS RIDES THE GPS STRING INSTEAD OF GETTING ITS OWN ENDPOINT
//
// A second Bridge.provide() would mean a second RPC poll from the Linux side
// on a link where one Serial.available() already costs ~595 ms. The host
// polls this endpoint once a second anyway, and the contract for the reply is
// explicitly open-ended: parse_gps_telemetry() short-circuits on parts[0] for
// NO_FIX and reads only parts[1..4] for FIX_OK, so trailing fields are ignored
// by design - the receiver diagnostics above already use that room.
//
//   UI  monotonic START press counter. Never a level and never an edge: a
//       press lasts a few hundred ms and the host polls at ~1 Hz, so a level
//       would be missed about as often as it was seen. The host compares this
//       against the value it read last, and cannot miss one.
//   TP  1 when a touch controller answered the boot probe, else 0.
//   RC  number of FS| records this sketch has PARSED, not received. The host
//       cannot otherwise tell a delivered record from a dropped one: the panel
//       link is a TCP socket into arduino-router, so a write succeeds whether
//       or not the MCU ever collected the bytes. That gap has bitten this
//       project before - senders reported success while the panel kept showing
//       dashes - and a counter the parser increments is the only evidence on
//       the wire that a push actually landed.
//   TZ  last derived contact pressure.
//   SA  1 once the controller has answered an SPI read. TP without SA is this
//       unit's actual state: the panel detects touch but the SPI wires do not
//       carry, so presses work and coordinates do not.
//   IQ  live PENIRQ level.   IL  1 once PENIRQ has ever read low.
//       These two cost no SPI, so they work with touch compiled out. IL going
//       to 1 on a finger proves the controller is powered and its IRQ is wired;
//       IL stuck at 0 proves it is not, and no SPI change would help.
//   TY  panel Y of the last contact, -1 if there has been none. The bottom bar
//       starts at y=182, so a press on it should report TY in the 180s-230s; a
//       small TY means the axis is inverted on this panel.
//   Z1  raw pressure channel 1.        Z2  raw pressure channel 2.
//       The raw pair is what separates "no controller" from "controller
//       present but untouched" from "MISO stuck at a rail" - all three of
//       which produce TZ:0 and need different fixes.
//   rx  raw bytes seen on Serial1.  lines  complete newline-terminated lines.
//   csum  lines whose NMEA checksum validated.
//   gga  GGA sentences handed to parseGGA.  ovf  merged/overlong lines discarded.
//   age  seconds since the last parseGGA that published a position, -1 if
//       there has never been one. latest_gps_csv persists until the next
//       successful parse, so without this the host cannot tell a current
//       position from one minutes old - and a stale fix stapled to a fresh
//       soil sample mislocates it silently.
//   hi   bytes that arrived with bit 7 set.  raw  the last 48 bytes, escaped.
//       These two answer the question the counters cannot: rx>0 with lines=0
//       means bytes without framing, but corrupted NMEA and a floating pin
//       look identical in a count. hi=0 says the stream is 7-bit ASCII, so it
//       is NMEA and the fault is framing; hi near rx/2 says it is noise and
//       the wire is not connected. raw shows which, directly.
//       The same argument as Z1/Z2, applied to the GPS. publishNoFix() already
//       reports these, but it only runs once a line has COMPLETED - so in the
//       one failure that most needs explaining, a receiver delivering nothing,
//       the payload is the cold-start default and carries no counters at all.
//       "GPS unpowered", "TX not wired", "wrong baud" and "MCU wedged" then look
//       identical from the host. Reported here they are one glance apart:
//         rx=0                  nothing on the wire. Power or wiring.
//         rx>0, lines=0         bytes but never a newline. Baud mismatch, or
//                               two drivers contending on the RX pin.
//         lines>0, csum=0       framing right, content corrupt - the drain is
//                               losing characters mid-sentence.
//         csum>0                receiver healthy; anything left is satellite
//                               lock, which is sky and time, not wiring.
//       Written with '=' rather than ':' deliberately: parse_ui_event() splits
//       on ':' and skips what has none, so these stay diagnostics and can never
//       be mistaken for an operator-control field.
String get_gps_data() {
  char raw[GPS_RAW_WINDOW + 1];
  renderRawWindow(raw, sizeof(raw));
  // 288: the five counters are 76 characters at UINT32_MAX, hi= adds 13, and
  // raw= adds the 48-byte window. raw goes LAST because it is the only
  // free-form field - anything after it would be harder to find.
  char suffix[288];
  snprintf(suffix, sizeof(suffix),
           ",UI:%lu,TP:%d,SA:%d,TZ:%u,Z1:%u,Z2:%u,TY:%d,IQ:%u,IL:%d,RC:%lu"
           ",rx=%lu,lines=%lu,csum=%lu,gga=%lu,ovf=%lu,hi=%lu,age=%ld,raw=%s",
           (unsigned long)pressCount, touchPresent ? 1 : 0, spiAnswering ? 1 : 0,
           (unsigned)lastTouchZ,
           (unsigned)lastTouchZ1, (unsigned)lastTouchZ2, (int)lastTouchY,
           (unsigned)irqLevel, irqEverLow ? 1 : 0,
           (unsigned long)recordCount,
           (unsigned long)gpsBytes, (unsigned long)gpsLines,
           (unsigned long)gpsChecksumOk, (unsigned long)gpsGgaSeen,
           (unsigned long)gpsOverflows, (unsigned long)gpsHighBit,
           gpsHaveFix ? (long)((millis() - gpsLastFixMs) / 1000UL) : -1L, raw);
  return latest_gps_csv + String(suffix);
}


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

// Draw one value into its own cleared box. Width is generous enough for the
// longest value each field can hold, so a shrinking number cannot leave the
// tail of the previous one behind it.
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

// Has this string changed since it was last drawn?
//
// The whole flicker fix in one idea. Every dynamic region below repaints by
// clearing its rectangle and drawing into it - which is correct, and invisible
// when the contents actually changed, and a visible wipe when they did not.
// renderValues() runs once a second so the age counter stays truthful, and
// almost none of the panel changes in that second.
//
// Each caller keeps a small buffer of what it last put on the glass and repaints
// only on a difference, so a still panel issues no writes at all.
static bool changedSince(char *cache, size_t cap, const char *now) {
  if (strncmp(cache, now, cap - 1) == 0) {
    return false;
  }
  copyField(cache, cap, now);
  return true;
}

// Colour for one progress-strip character.
//
//   V a stored VALID sample     S stored but flagged      R being taken now
//   -  not yet reached
//
// S and R are both amber deliberately: from the operator's side they mean the
// same thing - that tile is not finished business - and inventing a fourth
// colour for the difference would cost more than it explains at arm's length.
static uint16_t segmentColour(char code) {
  switch (code) {
    case 'V': return COL_GOOD;
    case 'S': return COL_WARN;
    case 'R': return COL_WARN_D;
    default:  return COL_CARD;
  }
}

// Traffic-light colour for one zone letter from the host's grid string.
static uint16_t zoneColour(char code) {
  switch (code) {
    case 'G': return COL_GOOD;
    case 'A': return COL_WARN;
    case 'R': return COL_BAD;
    default:  return COL_DIM;    // '?' - a status word this panel does not know
  }
}

// The step bar: one tile per planned sample, across the full width.
//
// Reads its length from the host's string rather than assuming five, so a
// session configured for a different sample count still draws a correct strip.
static void renderProgress() {
  static char drawn[12] = "\x01";      // impossible value, so the first pass draws
  if (!changedSince(drawn, sizeof(drawn), progressSegments)) {
    return;
  }
  size_t count = strlen(progressSegments);
  tft.fillRect(MARGIN, PROG_Y, PANEL_W - 2 * MARGIN, PROG_H, COL_BG);
  if (count == 0) {
    return;
  }
  int16_t span = PANEL_W - 2 * MARGIN;
  int16_t tile = (int16_t)((span - (int16_t)(count - 1) * PROG_GAP) / (int16_t)count);
  if (tile < 4) tile = 4;
  int16_t x = MARGIN;
  for (size_t i = 0; i < count; i++) {
    tft.fillRoundRect(x, PROG_Y, tile, PROG_H, 3, segmentColour(progressSegments[i]));
    x += tile + PROG_GAP;
  }
}

// The result view's zone map: one coloured tile per zone.
//
// This is the interpolated field reduced to the only thing readable outdoors -
// which areas are fine and which are not. It draws exactly the statuses the
// zone engine produced; the ordering matches the zone list, so tile n is
// zone n in the written report.
static void renderZoneGrid(int16_t x, int16_t y, int16_t w, int16_t h) {
  size_t count = strlen(zoneStatuses);
  tft.fillRect(x, y, w, h, COL_CARD);
  if (count == 0) {
    label(x, y + (h - CHAR_H) / 2, "NO ZONES", COL_DIM, 1);
    return;
  }
  // Lay out in up to two rows so a long zone list stays legible rather than
  // shrinking to slivers.
  size_t perRow = count > 4 ? (count + 1) / 2 : count;
  size_t rows = (count + perRow - 1) / perRow;
  int16_t gap = 3;
  int16_t tileW = (int16_t)((w - (int16_t)(perRow - 1) * gap) / (int16_t)perRow);
  int16_t tileH = (int16_t)((h - (int16_t)(rows - 1) * gap) / (int16_t)rows);
  if (tileW < 4) tileW = 4;
  if (tileH < 4) tileH = 4;

  for (size_t i = 0; i < count; i++) {
    size_t row = i / perRow, col = i % perRow;
    tft.fillRoundRect(x + (int16_t)col * (tileW + gap),
                      y + (int16_t)row * (tileH + gap),
                      tileW, tileH, 2, zoneColour(zoneStatuses[i]));
  }
}

// Three-band health scale with a marker at the score.
//
// The bar is always green|amber|red left to right; the marker says where this
// field sits on it. That is readable at a glance in a way a bare percentage is
// not, and it does not restate the number - it places it.
static void renderHealthScale(int16_t x, int16_t y, int16_t w, int16_t h) {
  int16_t band = w / 3;
  tft.fillRect(x, y, band, h, COL_BAD);
  tft.fillRect(x + band, y, band, h, COL_WARN);
  tft.fillRect(x + 2 * band, y, w - 2 * band, h, COL_GOOD);
  if (healthScore >= 0.0f) {
    float clamped = healthScore < 0.0f ? 0.0f : (healthScore > 1.0f ? 1.0f : healthScore);
    int16_t mx = x + (int16_t)((w - 3) * clamped);
    tft.fillRect(mx, y - 3, 3, h + 6, COL_TEXT);
  }
}

// Static chrome: background, title, card shapes, fixed labels. Drawn once.
static void renderChrome() {
  tft.fillScreen(COL_BG);

  // Header band: product mark left, the sample counter right at size 3.
  tft.fillRect(0, HEADER_Y, PANEL_W, HEADER_H, COL_CARD);
  label(MARGIN + 2, 7, "FIELDSENSE", COL_ACCENT, 2);
  tft.drawFastHLine(0, HEADER_H, PANEL_W, COL_DIM);

  // The middle card is drawn per-state by renderValues, because the sampling
  // view and the result view are different shapes rather than the same shape
  // with different numbers.
  barShapeKnown = false;
}

// Sampling view: the live probe channels, two columns.
// The card background and its fixed labels. Drawn when the view appears, never
// on a periodic repaint - painting these every second is what wiped the card.
static void renderSoilChrome() {
  tft.fillRoundRect(MARGIN, SOIL_Y, PANEL_W - 2 * MARGIN, SOIL_H, 4, COL_CARD);
  label(SOIL_COL_A, SOIL_Y + 5,                  "MOISTURE", COL_DIM, 1);
  label(SOIL_COL_A, SOIL_Y + 5 + SOIL_ROW_H,     "PH",       COL_DIM, 1);
  label(SOIL_COL_A, SOIL_Y + 5 + SOIL_ROW_H * 2, "EC",       COL_DIM, 1);
  label(SOIL_COL_B, SOIL_Y + 5,                  "N",        COL_DIM, 1);
  label(SOIL_COL_B, SOIL_Y + 5 + SOIL_ROW_H,     "P",        COL_DIM, 1);
  label(SOIL_COL_B, SOIL_Y + 5 + SOIL_ROW_H * 2, "K",        COL_DIM, 1);
  label(SOIL_COL_A, SOIL_Y + 5 + SOIL_ROW_H * 3, "SAMPLES",  COL_DIM, 1);
  label(SOIL_COL_B, SOIL_Y + 5 + SOIL_ROW_H * 3, "SITES",    COL_DIM, 1);
}

// Only the value boxes, and only when a value actually moved. Each putValue
// clears its own small rectangle first, so a shrinking number cannot leave the
// tail of the previous one behind.
static void renderSoilCard() {
  static char drawn[64] = "\x01";
  char now[64];
  snprintf(now, sizeof(now), "%.1f|%.2f|%.2f|%ld|%ld|%ld|%ld|%ld|%ld",
           (double)soilMoisture, (double)soilPh, (double)soilEc,
           (long)soilN, (long)soilP, (long)soilK,
           (long)totalSamples, (long)validSamples, (long)distinctLocs);
  if (!changedSince(drawn, sizeof(drawn), now)) {
    return;
  }

  int16_t vA = SOIL_COL_A + 62, vB = SOIL_COL_B + 22;
  putFloat(vA, SOIL_Y + 5,                  56, soilMoisture, 1, COL_TEXT);
  if (soilMoisture >= 0.0f) tft.print("%");
  putFloat(vA, SOIL_Y + 5 + SOIL_ROW_H,     56, soilPh,       2, COL_TEXT);
  putFloat(vA, SOIL_Y + 5 + SOIL_ROW_H * 2, 56, soilEc,       2, COL_TEXT);
  putInt(vB, SOIL_Y + 5,                    56, soilN, COL_TEXT);
  putInt(vB, SOIL_Y + 5 + SOIL_ROW_H,       56, soilP, COL_TEXT);
  putInt(vB, SOIL_Y + 5 + SOIL_ROW_H * 2,   56, soilK, COL_TEXT);

  putValue(vA, SOIL_Y + 5 + SOIL_ROW_H * 3, 56, CHAR_H, COL_CARD, COL_TEXT, 1);
  if (totalSamples < 0) {
    tft.print("--");
  } else {
    tft.print(totalSamples);
    if (validSamples >= 0) { tft.print(" OK "); tft.print(validSamples); }
  }
  putInt(SOIL_COL_B + 40, SOIL_Y + 5 + SOIL_ROW_H * 3, 42, distinctLocs, COL_TEXT);
}

// Result view: the score, its status badge, the scale, and the zone map.
static void renderResultChrome() {
  tft.fillRoundRect(MARGIN, SOIL_Y, PANEL_W - 2 * MARGIN, SOIL_H, 4, COL_CARD);
  label(PANEL_W / 2 + 6, SOIL_Y + 4, "ZONES", COL_DIM, 1);
}

static void renderResultCard() {
  static char drawn[64] = "\x01";
  char now[64];
  snprintf(now, sizeof(now), "%.2f|%s|%s",
           (double)healthScore, statusText, zoneStatuses);
  if (!changedSince(drawn, sizeof(drawn), now)) {
    return;
  }

  // Score, large. The one number a farmer reads first.
  char pct[8];
  if (healthScore >= 0.0f) {
    snprintf(pct, sizeof(pct), "%d%%", (int)(healthScore * 100.0f + 0.5f));
  } else {
    snprintf(pct, sizeof(pct), "--");
  }
  label(SOIL_COL_A, SOIL_Y + 6, pct, statusColour(), 3);

  // Status badge, filled in the same traffic-light colour.
  int16_t badgeW = (int16_t)(strlen(statusText) * CHAR_W + 10);
  if (badgeW > 108) badgeW = 108;
  tft.fillRoundRect(SOIL_COL_A, SOIL_Y + 34, badgeW, 14, 3, statusColour());
  drawClipped(SOIL_COL_A + 5, SOIL_Y + 38, badgeW - 10, statusText, COL_BG, 1);

  // Where that score sits on a green/amber/red scale.
  renderHealthScale(SOIL_COL_A, SOIL_Y + 26, 108, 5);

  // Zone map on the right half.
  renderZoneGrid(PANEL_W / 2 + 6, SOIL_Y + 15, PANEL_W / 2 - 6 - MARGIN - 6, SOIL_H - 20);
}

// The bottom bar is the single touch target. Green and full width when there
// is something to press; a flat state strip when the device is busy, so there
// is no target to press by mistake.
static void renderBarChrome(bool asButton) {
  if (asButton) {
    tft.fillRoundRect(MARGIN, BAR_Y, PANEL_W - 2 * MARGIN, BAR_H - 2, 8, COL_GOOD_D);
    tft.drawRoundRect(MARGIN, BAR_Y, PANEL_W - 2 * MARGIN, BAR_H - 2, 8, COL_GOOD);
  } else {
    tft.fillRoundRect(MARGIN, BAR_Y, PANEL_W - 2 * MARGIN, BAR_H - 2, 8, COL_CARD);
  }
  barIsButton = asButton;
  barShapeKnown = true;
}

// Everything that can change. Called on new data, and once a second so the age
// counter stays truthful.
static void renderValues() {
  char buf[48];

  // Header right: the sample counter, large.
  {
    static char drawn[16] = "\x01";
    if (sampleIndex > 0 && plannedSamples > 0) {
      snprintf(buf, sizeof(buf), "%ld/%ld", (long)sampleIndex, (long)plannedSamples);
    } else {
      buf[0] = '\0';
    }
    if (changedSince(drawn, sizeof(drawn), buf)) {
      putValue(PANEL_W - 118, 4, 112, CHAR_H * 3, COL_CARD, COL_TEXT, 3);
      if (buf[0]) {
        int16_t width = (int16_t)(strlen(buf) * CHAR_W * 3);
        tft.setCursor(PANEL_W - MARGIN - 2 - width, 4);
        tft.print(buf);
      }
    }
  }

  renderProgress();

  // GPS strip. Fix state, satellites and HDOP come from this sketch's own GGA
  // parse - the host is never asked what the receiver on this MCU is doing.
  bool haveFix = (strncmp(latest_gps_csv.c_str(), "FIX_OK", 6) == 0);
  {
    // Fix state, satellites and HDOP change on the receiver's schedule, not
    // once a second. Repainting the whole strip regardless was a full-width
    // wipe for content that was usually identical.
    static char drawn[40] = "\x01";
    snprintf(buf, sizeof(buf), "%d|%s|%s", haveFix ? 1 : 0,
             gpsSatsText(), gpsHdopText());
    if (changedSince(drawn, sizeof(drawn), buf)) {
      putValue(MARGIN, GPS_Y, PANEL_W - 2 * MARGIN - 48, CHAR_H, COL_BG, COL_DIM, 1);
      tft.setTextColor(haveFix ? COL_GOOD : COL_WARN);
      tft.print(haveFix ? "GPS FIX" : "GPS SEARCHING");
      tft.setTextColor(COL_DIM);
      tft.print("  SAT ");
      tft.print(gpsSatsText());
      tft.print("  HDOP ");
      tft.print(gpsHdopText());
    }
  }

  bool everReceived = recordCount > 0;
  uint32_t ageS = everReceived ? (millis() - lastRecordMs) / 1000 : 0;
  if (!everReceived) {
    snprintf(buf, sizeof(buf), "NO HOST");
  } else {
    snprintf(buf, sizeof(buf), "%lus", (unsigned long)ageS);
  }
  {
    // The only region that legitimately changes every second. It is 6 characters
    // wide, so a repaint here is invisible - but gate it anyway so a panel with
    // a settled age counter issues no writes at all.
    static char drawn[16] = "\x01";
    if (changedSince(drawn, sizeof(drawn), buf)) {
      int16_t linkW = (int16_t)(strlen(buf) * CHAR_W);
      putValue(PANEL_W - MARGIN - 48, GPS_Y, 48, CHAR_H, COL_BG,
               everReceived ? (ageS > 30 ? COL_WARN : COL_DIM) : COL_WARN, 1);
      tft.setCursor(PANEL_W - MARGIN - linkW, GPS_Y);
      tft.print(buf);
    }
  }

  // THE TEASER. One actionable line, as large as it will go.
  uint16_t actionColour = COL_TEXT;
  if (!strcmp(workflowState, "ERROR"))             actionColour = COL_BAD;
  else if (!strcmp(workflowState, "MEASURING"))    actionColour = COL_ACCENT;
  else if (!strcmp(workflowState, "SAMPLE_SAVED")) actionColour = COL_GOOD;
  else if (!strcmp(workflowState, "PROCESSING"))   actionColour = COL_ACCENT;
  else if (!strcmp(lastQuality, "RETRY"))          actionColour = COL_WARN;
  {
    // The instruction changes on a state change, not on a clock. Clearing this
    // 308x48 band every second was the largest single wipe on the panel.
    static char drawn[48] = "\x01";
    static uint16_t drawnColour = 0;
    if (changedSince(drawn, sizeof(drawn), actionLine) || actionColour != drawnColour) {
      drawnColour = actionColour;
      tft.fillRect(MARGIN, ACTION_Y, PANEL_W - 2 * MARGIN, ACTION_H, COL_BG);
      drawCentered(MARGIN, ACTION_Y, PANEL_W - 2 * MARGIN, ACTION_H,
                   actionLine, actionColour, 3);
    }
  }

  // Middle card: which view depends on whether the run has produced a result.
  // The card's BACKGROUND and labels are drawn only when the view changes; the
  // values redraw themselves only when they move. Previously the whole card was
  // repainted every second, which is what wiped it.
  bool showResult = !strcmp(workflowState, "RESULT");
  static int8_t lastCardKind = -1;
  int8_t cardKind = showResult ? 1 : 0;
  if (cardKind != lastCardKind) {
    lastCardKind = cardKind;
    tft.fillRect(MARGIN, SOIL_Y, PANEL_W - 2 * MARGIN, SOIL_H, COL_BG);
    if (showResult) {
      renderResultChrome();
    } else {
      renderSoilChrome();
    }
  }
  if (showResult) {
    renderResultCard();
  } else {
    renderSoilCard();
  }

  // Bottom bar. A label means there is something to press.
  bool wantButton = (buttonLabel[0] != '\0');
  bool barReshaped = (!barShapeKnown || wantButton != barIsButton);
  if (barReshaped) {
    renderBarChrome(wantButton);
  }

  if (wantButton) {
    // The label changes on a state change. Repainting the button face every
    // second made the one element an operator is about to touch the least
    // stable thing on the panel.
    static char drawn[24] = "\x01";
    if (barReshaped || changedSince(drawn, sizeof(drawn), buttonLabel)) {
      tft.fillRoundRect(MARGIN + 3, BAR_Y + 3, PANEL_W - 2 * MARGIN - 6, BAR_H - 8, 6, COL_GOOD_D);
      drawCentered(MARGIN, BAR_Y, PANEL_W - 2 * MARGIN, BAR_H - 2, buttonLabel, COL_BG, 3);
    }
  } else {
    static char drawn[48] = "\x01";
    snprintf(buf, sizeof(buf), "%s|%s|%ld|%d", workflowState, lastQuality,
             (long)offlineMode, touchPresent ? 1 : 0);
    if (barReshaped || changedSince(drawn, sizeof(drawn), buf)) {
      tft.fillRect(MARGIN + 3, BAR_Y + 3, PANEL_W - 2 * MARGIN - 6, BAR_H - 8, COL_CARD);
      int16_t qualityW = (int16_t)(strlen(lastQuality) * CHAR_W);
      int16_t stateW = PANEL_W - MARGIN - 8 - qualityW - SOIL_COL_A - 6;
      drawClipped(SOIL_COL_A, BAR_Y + 12, stateW, workflowState, COL_ACCENT, 2);
      if (lastQuality[0]) {
        label(PANEL_W - MARGIN - 8 - qualityW, BAR_Y + 16, lastQuality,
              qualityColour(), 1);
      }
      if (offlineMode == 1) {
        label(SOIL_COL_A, BAR_Y + 36, "OFFLINE", COL_GOOD, 1);
      }
      if (!touchPresent) {
        const char *note = "NO TOUCH";
        label(PANEL_W - MARGIN - 8 - (int16_t)(strlen(note) * CHAR_W),
              BAR_Y + 36, note, COL_WARN, 1);
      }
    }
  }
}

// ------------------------------------------------------------- lifecycle

void setup() {
  pinMode(TFT_LED, OUTPUT);
  digitalWrite(TFT_LED, HIGH);
  delay(500);
  SPI.begin();

  // init() takes the panel's NATIVE dimensions - the glass is 240x320 whatever
  // orientation it is driven in. setRotation(1) is what makes the drawing
  // surface 320x240, which is what PANEL_W/PANEL_H describe and what every
  // coordinate in this file is written against.
  tft.init(240, 320);
  tft.setRotation(PANEL_ROTATION);
  tft.invertDisplay(false);

  // Probe the touch controller after SPI is up but before anything is drawn,
  // so the first frame already knows whether to advertise a touch target.
  probeTouch();

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
  // panel repaints on new data or once a second, whichever comes first, and a
  // record is ~135 bytes that can wait 400 ms.
  //
  // The operator's START control is serviced in this same tight window, and
  // that is the whole reason it can be responsive at all. A press held for
  // TOUCH_HOLD_MS spans about ninety passes of this loop; servicing it once
  // per outer pass instead would sample it roughly once a second and miss
  // ordinary presses.
  uint32_t drainUntil = millis() + GPS_DRAIN_MS;
  while ((int32_t)(millis() - drainUntil) < 0) {
    serviceGPS();
    serviceTouchIrq();
    serviceOperatorInput();
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
    serviceOperatorInput();

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
  // this costs a few hundred bytes of SPI instead of 153,600.
  static uint32_t lastPaint = 0;
  if (dirty || millis() - lastPaint > 1000) {
    dirty = false;
    lastPaint = millis();
    renderValues();
  }
}
