#include "Arduino_RouterBridge.h"

#define GPS_SERIAL Serial1
String latest_gps_csv = "NO_FIX,0.0,0.0,0,0.0"; 

void setup() {
    Bridge.begin();
    Bridge.provide("get_gps_data", get_gps_data);
    
    // NEO-M8N default baud rate is usually 9600
    GPS_SERIAL.begin(9600); 
}

void loop() {
    if (GPS_SERIAL.available() > 0) {
        String line = GPS_SERIAL.readStringUntil('\n');
        line.trim();
        
        if (line.startsWith("$GNGGA") || line.startsWith("$GPGGA")) {
            parse_gga_sentence(line);
        }
    }
}

// Bridge Endpoint for Python to call
String get_gps_data() {
    return latest_gps_csv;
}

// Ground-level CSV parser to avoid heavy external libraries
void parse_gga_sentence(String gga) {
    int indices[15];
    int commaCount = 0;
    
    // Map the commas to isolate the target fields
    for (int i = 0; i < gga.length(); i++) {
        if (gga.charAt(i) == ',') {
            indices[commaCount] = i;
            commaCount++;
            if (commaCount >= 14) break;
        }
    }
    
    // GGA Index: 2=Lat, 3=N/S, 4=Lon, 5=E/W, 6=Fix, 7=Sats, 8=HDOP
    if (commaCount >= 8) {
        String lat = gga.substring(indices[1] + 1, indices[2]);
        String latDir = gga.substring(indices[2] + 1, indices[3]);
        String lon = gga.substring(indices[3] + 1, indices[4]);
        String lonDir = gga.substring(indices[4] + 1, indices[5]);
        String fix = gga.substring(indices[5] + 1, indices[6]);
        String sats = gga.substring(indices[6] + 1, indices[7]);
        String hdop = gga.substring(indices[7] + 1, indices[8]);
        
        String fixStatus = (fix == "0" || fix == "") ? "NO_FIX" : "FIX_OK";
        
        // Format: Status, Lat+Dir, Lon+Dir, Sats, HDOP
        latest_gps_csv = fixStatus + "," + lat + latDir + "," + lon + lonDir + ",Sats:" + sats + ",HDOP:" + hdop;
    }
}