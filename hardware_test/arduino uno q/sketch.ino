#include "Arduino_RouterBridge.h"

#define HW_SERIAL Serial1 

String loopback_status = "WAITING";

void setup() {
    Bridge.begin();
    Bridge.provide("get_uart_status", get_uart_status);
    HW_SERIAL.begin(115200); 
}

void loop() {
    // 1. Reset the status at the start of every cycle
    loopback_status = "FAIL: DISCONNECTED";
    
    // 2. Flush any old data out of the RX buffer
    while(HW_SERIAL.available() > 0) {
        HW_SERIAL.read();
    }

    // 3. Send a ping out the TX pin
    HW_SERIAL.println("PING");
    
    // 4. Wait a moment for it to cross the wire
    delay(20); 
    
    // 5. Check if the RX pin caught it
    if (HW_SERIAL.available() > 0) {
        String received = HW_SERIAL.readStringUntil('\n');
        received.trim();
        
        if (received == "PING") {
            loopback_status = "PASS: TX/RX WORKING";
        } else {
            loopback_status = "FAIL: GARBAGE DATA";
        }
    }
    
    delay(1000);
}

String get_uart_status() {
    return loopback_status;
}