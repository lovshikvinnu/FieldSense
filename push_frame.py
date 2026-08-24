import os

port = '/dev/ttyGS0' # Remember to change to /dev/ttyACM0 if needed

print(f"1. Generating 153,600 bytes of FieldSense Green (0x07E0)...")
# RGB565 Green is 0x07E0. 
# Our STM32 sketch reads MSB first, then LSB.
# MSB = 0x07, LSB = 0xE0
green_pixel = bytes([0x07, 0xE0])
frame_bytes = green_pixel * 76800  # 76,800 pixels = 153,600 bytes

print(f"2. Configuring native Serial Port {port}...")
os.system(f"stty -F {port} 115200 raw -echo")

print("3. Blasting frame to STM32...")
try:
    with open(port, 'wb') as s:
        s.write(b'\xAA')       # Magic trigger byte to open the window
        s.write(frame_bytes)   # Push the entire frame
        s.flush()
    print("Success! The screen should snap to solid green.")
except Exception as e:
    print(f"Failed to write to Serial port: {e}")
