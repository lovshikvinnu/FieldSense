#include "Arduino_RouterBridge.h"
#include <ModbusMaster.h>

#define HW_SERIAL Serial1 
#define MAX485_RE_DE 7    

// Global Declarations (Fixes the scope error)
ModbusMaster node;
String soil_data = "INITIALIZING...";

// Callbacks to toggle the MAX485 transmit/receive states
void preTransmission() { digitalWrite(MAX485_RE_DE, HIGH); }
void postTransmission() { digitalWrite(MAX485_RE_DE, LOW); }

void setup() {
    Bridge.begin();
    Bridge.provide("get_soil_data", get_soil_data); 
    
    pinMode(MAX485_RE_DE, OUTPUT);
    digitalWrite(MAX485_RE_DE, LOW);

    // Initialize UART at 9600 baud for the JXBS sensor
    HW_SERIAL.begin(9600); 
    node.begin(1, HW_SERIAL); // Sensor Slave ID is 1
    node.preTransmission(preTransmission);
    node.postTransmission(postTransmission);
}

void loop() {
    float ph = 0.0, moisture = 0.0, temp = 0.0;
    uint16_t ec = 0, n = 0, p = 0, k = 0;
    bool success = true;

    // 1. Read pH (Register 0x0006)
    if (node.readHoldingRegisters(0x0006, 1) == node.ku8MBSuccess) {
        ph = node.getResponseBuffer(0) / 100.0;
    } else { success = false; }

    // 2. Read Moisture, Temperature & EC (Registers 0x0012 to 0x0015)
    if (node.readHoldingRegisters(0x0012, 4) == node.ku8MBSuccess) {
        moisture = node.getResponseBuffer(0) / 10.0;
        temp     = node.getResponseBuffer(1) / 10.0;
        // Buffer index 2 is 0x0014 (reserved/status)
        ec       = node.getResponseBuffer(3);
    } else { success = false; }

    // 3. Read NPK (Registers 0x001E to 0x0020)
    if (node.readHoldingRegisters(0x001E, 3) == node.ku8MBSuccess) {
        n = node.getResponseBuffer(0);
        p = node.getResponseBuffer(1);
        k = node.getResponseBuffer(2);
    } else { success = false; }

    if (success) {
        // Structured JSON-style output for easy parsing in Python
        soil_data = "{\"temp\":" + String(temp, 1) + 
                    ",\"moisture\":" + String(moisture, 1) + 
                    ",\"ph\":" + String(ph, 2) + 
                    ",\"ec\":" + String(ec) + 
                    ",\"n\":" + String(n) + 
                    ",\"p\":" + String(p) + 
                    ",\"k\":" + String(k) + "}";
    } else {
        soil_data = "{\"error\":\"MODBUS_READ_FAILED\"}";
    }

    delay(2000);
}

// Function called by Python via RouterBridge
String get_soil_data() {
    return soil_data;
}