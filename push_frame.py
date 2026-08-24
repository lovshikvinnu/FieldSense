import os
import time

port = '/dev/ttyGS0'

print(f"1. Generating 153,600 bytes of FieldSense Green (0x07E0)...")
green_pixel = bytes([0x07, 0xE0])
frame_bytes = green_pixel * 76800  # 153,600 bytes

print(f"2. Configuring native Serial Port {port}...")
os.system(f"stty -F {port} 115200 raw -echo")

print("3. Blasting frame to STM32 with handshake delay...")
try:
    with open(port, 'wb') as s:
        # Send trigger and flush
        s.write(b'\xAA')       
        s.flush()
        
        # Give the STM32 50ms to catch up and open the address window
        time.sleep(0.05) 
        
        # Now blast the heavy pixel data
        s.write(frame_bytes)   
        s.flush()
        
    print("Success! Check the screen now.")
except Exception as e:
    print(f"Failed to write to Serial port: {e}")
