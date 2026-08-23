import serial
import time

TX_PORT = "COM10"  # ESP-01 CH340 Programmer (TTL TX -> MAX485 DI)
RX_PORT = "COM8"   # FT232 RS485 Adapter (RS485 A/B Receiver)
BAUDRATE = 9600

test_payloads = [
    b"HELLO_MAX485\n",
    b"\x01\x03\x00\x1E\x00\x01\xE4\x0C",  # Modbus query frame
    b"FIELDSENSE_HARDWARE_VERIFIED\n"
]

# Initialize TX Serial (COM10) with CH340 handshake bypass
ser_tx = serial.Serial(
    port=TX_PORT,
    baudrate=BAUDRATE,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=1,
    xonxoff=False,
    rtscts=False,
    dsrdtr=False
)

# Initialize RX Serial (COM8)
ser_rx = serial.Serial(
    port=RX_PORT,
    baudrate=BAUDRATE,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=2
)

try:
    ser_tx.reset_output_buffer()
    ser_rx.reset_input_buffer()
    time.sleep(0.1)

    print(f"Starting Transmit Test: {TX_PORT} (MAX485 TX) -> {RX_PORT} (RS485 RX)\n" + "-"*60)

    for i, payload in enumerate(test_payloads, 1):
        print(f"Test {i}: Sending -> {payload}")
        ser_tx.write(payload)
        ser_tx.flush()

        time.sleep(0.05)  # Allow transmission to settle

        received = ser_rx.read(len(payload))
        print(f"Test {i}: Received -> {received}")

        if received == payload:
            print(f"Test {i} Result: PASS (Exact Match)\n")
        else:
            print(f"Test {i} Result: FAIL (Mismatch or Timeout)\n")

finally:
    ser_tx.close()
    ser_rx.close()
    print("Ports closed.")