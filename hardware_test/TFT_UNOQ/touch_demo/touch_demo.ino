#include <SPI.h>

#undef MOSI
#undef MISO
#undef SCK

#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>
#include <XPT2046_Touchscreen.h>

// 1. Display Pins
//
// PIN CONFLICT, RESOLVED HERE. The MAX485 RS485 transceiver drives its shared
// DE/RE direction line from digital pin 7 (see the soil sensor sketch and
// docs/HARDWARE.md section 6). This sketch previously also claimed pin 7 for
// the display backlight. Both peripherals are present in the assembled
// FieldSense unit, so on the same MCU that single line would have driven the
// transceiver into transmit whenever the backlight was on, jamming the Modbus
// bus, while every soil read would have flickered the screen.
//
// The backlight moves to pin 6, which no other FieldSense peripheral claims.
// Pin 7 belongs to MAX485_RE_DE and nothing else.
#define TFT_CS    10
#define TFT_DC    9
#define TFT_RST   8
#define TFT_LED   6   // was 7 — see the pin conflict note above

// 2. Touch Pins
#define TOUCH_CS  4
#define TOUCH_IRQ 2

// 3. Instantiate objects (Both share the hardware &SPI bus)
Adafruit_ST7789 tft = Adafruit_ST7789(&SPI, TFT_CS, TFT_DC, TFT_RST);
XPT2046_Touchscreen ts(TOUCH_CS, TOUCH_IRQ);

void setup() {
  Serial.begin(115200);

  pinMode(TFT_LED, OUTPUT);
  digitalWrite(TFT_LED, HIGH);

  delay(500); 

  // Initialize the shared SPI bus once
  SPI.begin();

  // Initialize Touch
  ts.begin();
  ts.setRotation(1); // Match display rotation

  // Initialize Display
  tft.init(240, 320);
  tft.setRotation(1); 
  tft.invertDisplay(false); // Keeps your corrected color matrix

  // Draw Base UI
  tft.fillScreen(ST77XX_BLACK);
  tft.setCursor(10, 10);
  tft.setTextColor(ST77XX_GREEN);
  tft.setTextSize(2);
  tft.println("Touch Diagnostics");
  tft.drawFastHLine(0, 35, 320, ST77XX_WHITE);
}

void loop() {
  if (ts.touched()) {
    TS_Point p = ts.getPoint();

    // 1. Z-Axis Pressure Filter
    // Ignore floating noise, ghost touches, or lifted fingers
    // (Adjust the 400 threshold up or down based on your Serial Monitor readings)
    if (p.z < 400 || p.z > 4000) {
     // return; 
    }

    // 2. Map the coordinates (Keep your calibrated values here)
    int mapped_x = map(p.x, 200, 3700, 320, 0);
    int mapped_y = map(p.y, 200, 3700, 240, 0);

    // 3. Constrain the data
    // Prevents rogue edge-touches from wrapping around or shooting across the screen
    mapped_x = constrain(mapped_x, 0, 320);
    mapped_y = constrain(mapped_y, 0, 240);

    // Draw the dot
    tft.fillCircle(mapped_x, mapped_y, 3, ST77XX_CYAN);
    
    // Debugging output
    Serial.print("X: "); Serial.print(mapped_x);
    Serial.print(" | Y: "); Serial.print(mapped_y);
    Serial.print(" | Pressure: "); Serial.println(p.z);
    
    delay(10); 
  }
}