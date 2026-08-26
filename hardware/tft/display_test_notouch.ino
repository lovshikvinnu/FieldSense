#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>
#include <SPI.h>

#define TFT_CS   15
#define TFT_DC    2
#define TFT_RST   4

Adafruit_ST7789 tft = Adafruit_ST7789(TFT_CS, TFT_DC, TFT_RST);

void setup() {
  Serial.begin(115200);

  // Initialize ST7789 with standard 240x320 resolution
  tft.init(240, 320);
  tft.setRotation(1); // True Landscape (320 wide x 240 high)

  // Full Screen Refresh
  tft.fillScreen(ST77XX_BLACK);
  delay(200);

  // Border check (draws around the exact perimeter to check offsets)
  tft.drawRect(0, 0, 320, 240, ST77XX_WHITE);

  // Color test bars
  tft.fillRect(10, 10, 60, 40, ST77XX_RED);
  tft.fillRect(80, 10, 60, 40, ST77XX_GREEN);
  tft.fillRect(150, 10, 60, 40, ST77XX_BLUE);
  tft.fillRect(220, 10, 60, 40, ST77XX_YELLOW);

  // Text Rendering
  tft.setCursor(20, 80);
  tft.setTextColor(ST77XX_WHITE);
  tft.setTextSize(2);
  tft.println("FIELDSENSE AI");

  tft.setCursor(20, 115);
  tft.setTextColor(ST77XX_GREEN);
  tft.setTextSize(2);
  tft.println("2.8in TFT Display");

  tft.setCursor(20, 150);
  tft.setTextColor(ST77XX_CYAN);
  tft.setTextSize(1);
  tft.println("Driver: ST7789V / 320x240 Native");
}

void loop() {
}