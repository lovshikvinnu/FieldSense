import os
import sys

# Import your existing display tools
from fieldsense.hardware import display_bridge as bridge

html_path = "artifacts/field_test_map.html"
port = '/dev/ttyS0' # Change to /dev/ttyACM0 if needed

print(f"1. Rendering {html_path} to raw pixels in memory...")
# Capture the 240x320 frame exactly like your main pipeline does
width, height, rgb, _ = bridge.capture_or_panel(html_path, 240, 320, settle_ms=1000)

print("2. Converting to RGB565 format...")
# Convert to 'little' endian since your bridge supports it
frame_little = bridge.rgb_to_rgb565(rgb, "little")

# Swap bytes (Little Endian to Big Endian) so the STM32 sketch reads it perfectly
frame_bytes = bytearray(len(frame_little))
frame_bytes[0::2] = frame_little[1::2] # Move MSB
frame_bytes[1::2] = frame_little[0::2] # Move LSB

print(f"3. Configuring native Serial Port {port}...")
os.system(f"stty -F {port} 115200 raw -echo")

print(f"4. Blasting {len(frame_bytes)} bytes to STM32...")
try:
    with open(port, 'wb') as s:
        s.write(b'\xAA')       # Magic trigger byte for STM32
        s.write(frame_bytes)   # Push the entire 153,600 byte image
        s.flush()
    print("Success! Check the physical display.")
except Exception as e:
    print(f"Failed to write to Serial port: {e}")
