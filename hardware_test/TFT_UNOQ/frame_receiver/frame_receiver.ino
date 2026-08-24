// FieldSense AI - STM32 frame receiver for the 2.8" ST7789 SPI panel.
//
// WHY THIS EXISTS
//
// On the Arduino UNO Q the QRB2210 Linux MPU routes no SPI lines to the
// external headers: D11/D12/D13 and SPI2 land exclusively on the STM32U585.
// The Linux side therefore cannot ever expose this panel as /dev/fbN, and the
// `fb` target in fieldsense/hardware/display_bridge.py has nothing to write to
// (see the HARDWARE_SPEC_REQUIRED note at the top of that module). The MPU
// renders pixels; this sketch is the only thing that can put them on glass.
//
// PROTOCOL (v1) - must stay in lockstep with display_bridge.py
//
//   Header, 12 bytes, big-endian:
//     [0..1]   magic    0xAA 0xBB
//     [2]      version  0x01
//     [3]      format   0x01 = RGB565, big-endian on the wire
//     [4..5]   width    uint16   (240)
//     [6..7]   height   uint16   (320)
//     [8..9]   chunk    uint16   payload bytes per chunk, always even
//     [10..11] crc16    CCITT-FALSE over bytes [0..9]
//
//   Then ceil(width*height*2 / chunk) chunks, each:
//     [chunk payload bytes]  (final chunk may be short)
//     [crc16 CCITT-FALSE over that payload, 2 bytes big-endian]
//
//   This MCU replies one byte per header and per chunk:
//     0x06 ACK  accepted
//     0x15 NAK  rejected - bad CRC, bad geometry, or timeout
//
// The ACK is not decoration. Serial RX buffering here is a few hundred bytes
// against a 153,600 byte frame, so the host MUST block on each ACK. Blasting
// the frame open-loop with a fixed sleep - the approach in the old
// scratch script push_frame.py - overruns the buffer and shears the image.
//
// RGB565 arrives big-endian because that is the order the ST7789 wants on the
// wire, so writePixels() is called with bigEndian=true and no byte swapping
// happens on this side. Do not "fix" this to little-endian without also
// changing --byteorder on the host.
//
// PIN NOTES
//
// Backlight is D6, NOT D7. D7 is MAX485_RE_DE for the RS485 soil transceiver
// and is shared hardware in the assembled unit - driving it from here would
// jam the Modbus bus. This sketch never touches D7. Same resolution as
// sketch.ino; see the pin conflict comment there.

#include <SPI.h>

// The UNO Q core defines MOSI/MISO/SCK as macros that collide with the
// Adafruit headers. Same workaround as sketch.ino.
#undef MOSI
#undef MISO
#undef SCK

#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>

// ----------------------------------------------------------------- pins

#define TFT_CS    10
#define TFT_DC     9
#define TFT_RST    8
#define TFT_LED    6   // D7 belongs to MAX485_RE_DE - do not use it here

// ----------------------------------------------------------------- protocol

static const uint8_t  PROTO_MAGIC_0 = 0xAA;
static const uint8_t  PROTO_MAGIC_1 = 0xBB;
static const uint8_t  PROTO_VERSION = 0x01;
static const uint8_t  FORMAT_RGB565_BE = 0x01;

static const uint8_t  ACK = 0x06;
static const uint8_t  NAK = 0x15;

static const uint16_t PANEL_W = 240;
static const uint16_t PANEL_H = 320;

// Must be >= the host's --chunk-bytes. 4 KB is nothing against the U585's
// 786 KB SRAM and keeps the ACK round-trip count down to 38 for a full frame.
static const uint16_t MAX_CHUNK = 4096;

// Raise both this and --baud together, or the link desynchronises. 115200 is
// ~13 s for a full frame; 921600 brings that to ~1.7 s. Start at 115200,
// confirm a clean frame, then raise both sides.
static const uint32_t LINK_BAUD = 115200;

static const uint32_t BYTE_TIMEOUT_MS  = 2000;   // gap tolerance mid-transfer
static const uint32_t FRAME_TIMEOUT_MS = 30000;  // whole-frame ceiling

Adafruit_ST7789 tft = Adafruit_ST7789(&SPI, TFT_CS, TFT_DC, TFT_RST);

static uint8_t chunkBuf[MAX_CHUNK];

// ----------------------------------------------------------------- helpers

// CRC16 CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no final xor.
// Mirrors crc16_ccitt() in display_bridge.py exactly.
static uint16_t crc16_ccitt(const uint8_t *data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= (uint16_t)data[i] << 8;
    for (uint8_t bit = 0; bit < 8; bit++) {
      if (crc & 0x8000) {
        crc = (uint16_t)((crc << 1) ^ 0x1021);
      } else {
        crc = (uint16_t)(crc << 1);
      }
    }
  }
  return crc;
}

// Read exactly len bytes, or fail on an inter-byte gap longer than timeout_ms.
static bool readExact(uint8_t *dst, size_t len, uint32_t timeout_ms) {
  size_t got = 0;
  uint32_t lastProgress = millis();
  while (got < len) {
    int avail = Serial.available();
    if (avail > 0) {
      size_t want = len - got;
      if ((size_t)avail < want) {
        want = (size_t)avail;
      }
      int read = Serial.readBytes((char *)(dst + got), want);
      if (read > 0) {
        got += (size_t)read;
        lastProgress = millis();
      }
    } else if (millis() - lastProgress > timeout_ms) {
      return false;
    }
  }
  return true;
}

// Consume bytes until the two magic bytes land back to back. Lets the link
// resynchronise after a partial or aborted frame instead of wedging.
static bool syncToMagic(uint32_t timeout_ms) {
  uint32_t lastProgress = millis();
  uint8_t prev = 0x00;
  bool havePrev = false;
  while (millis() - lastProgress <= timeout_ms) {
    if (Serial.available() <= 0) {
      continue;
    }
    uint8_t b = (uint8_t)Serial.read();
    lastProgress = millis();
    if (havePrev && prev == PROTO_MAGIC_0 && b == PROTO_MAGIC_1) {
      return true;
    }
    prev = b;
    havePrev = true;
  }
  return false;
}

static void statusBanner(const char *line, uint16_t colour) {
  tft.fillScreen(ST77XX_BLACK);
  tft.setCursor(8, 8);
  tft.setTextColor(colour);
  tft.setTextSize(2);
  tft.println("FIELDSENSE");
  tft.setCursor(8, 34);
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_WHITE);
  tft.println(line);
}

// ----------------------------------------------------------------- lifecycle

void setup() {
  Serial.begin(LINK_BAUD);

  pinMode(TFT_LED, OUTPUT);
  digitalWrite(TFT_LED, HIGH);

  delay(500);
  SPI.begin();

  tft.init(PANEL_W, PANEL_H);
  // Rotation 0: native portrait, 240 wide x 320 tall. The host renders the
  // dashboard at 240x320, so any other rotation here would make the geometry
  // check below reject every frame.
  tft.setRotation(0);
  tft.invertDisplay(false);

  statusBanner("Waiting for frame on serial...", ST77XX_GREEN);
}

void loop() {
  if (!syncToMagic(BYTE_TIMEOUT_MS)) {
    return;  // nothing on the wire; come back next pass
  }

  // Magic already consumed. Pull the remaining 10 header bytes.
  uint8_t rest[10];
  if (!readExact(rest, sizeof(rest), BYTE_TIMEOUT_MS)) {
    Serial.write(NAK);
    return;
  }

  uint8_t header[12];
  header[0] = PROTO_MAGIC_0;
  header[1] = PROTO_MAGIC_1;
  memcpy(header + 2, rest, sizeof(rest));

  uint16_t wantCrc = (uint16_t)(header[10] << 8 | header[11]);
  if (crc16_ccitt(header, 10) != wantCrc) {
    Serial.write(NAK);
    return;
  }

  uint8_t  version = header[2];
  uint8_t  format  = header[3];
  uint16_t width   = (uint16_t)(header[4] << 8 | header[5]);
  uint16_t height  = (uint16_t)(header[6] << 8 | header[7]);
  uint16_t chunk   = (uint16_t)(header[8] << 8 | header[9]);

  // Reject rather than draw garbage. Same reasoning as the geometry guard in
  // write_framebuffer() on the host: a transposed or half-size frame is worse
  // than a refusal, because it looks like a working display.
  bool ok = version == PROTO_VERSION
         && format  == FORMAT_RGB565_BE
         && width   == tft.width()
         && height  == tft.height()
         && chunk   > 0
         && chunk   <= MAX_CHUNK
         && (chunk % 2) == 0;
  if (!ok) {
    Serial.write(NAK);
    return;
  }

  Serial.write(ACK);

  const uint32_t total = (uint32_t)width * (uint32_t)height * 2UL;
  uint32_t received = 0;
  uint32_t started = millis();
  bool aborted = false;

  tft.startWrite();
  tft.setAddrWindow(0, 0, width, height);

  while (received < total) {
    uint32_t remaining = total - received;
    uint16_t want = (remaining < (uint32_t)chunk) ? (uint16_t)remaining : chunk;

    if (!readExact(chunkBuf, want, BYTE_TIMEOUT_MS)) {
      aborted = true;
      break;
    }

    uint8_t crcBytes[2];
    if (!readExact(crcBytes, 2, BYTE_TIMEOUT_MS)) {
      aborted = true;
      break;
    }

    uint16_t expect = (uint16_t)(crcBytes[0] << 8 | crcBytes[1]);
    if (crc16_ccitt(chunkBuf, want) != expect) {
      // NAK and stop. The address window is already advanced, so resuming
      // mid-frame would tear; the host retries the whole frame instead.
      Serial.write(NAK);
      aborted = true;
      break;
    }

    // bigEndian=true: bytes are already in ST7789 wire order, no swap.
    tft.writePixels((uint16_t *)chunkBuf, want / 2, true, true);
    received += want;
    Serial.write(ACK);

    if (millis() - started > FRAME_TIMEOUT_MS) {
      aborted = true;
      break;
    }
  }

  tft.endWrite();

  if (aborted) {
    statusBanner("Frame aborted - retrying", ST77XX_RED);
  }
}
