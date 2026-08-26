import serial
import time

TX_PORT = "COM8"   # FT232 RS485 Adapter (Transmitter on RS485 bus)
RX_PORT = "COM10"  # ESP-01 CH340 Programmer (TTL RX from MAX485 RO)
BAUDRATE = 9600

test_payloads = [
    b"MAX485_RECEIVE_TEST\n",
    b"\x01\x03\x02\x00\x00\xB8\x44",  # Modbus response frame
    b"HARDWARE_RX_CONFIRMED\n"
]

# Initialize TX Serial (COM8)
ser_tx = serial.Serial(
    port=TX_PORT,
    baudrate=BAUDRATE,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=1
)

# Initialize RX Serial (COM10) with CH340 handshake bypass
ser_rx = serial.Serial(
    port=RX_PORT,
    baudrate=BAUDRATE,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=2,
    xonxoff=False,
    rtscts=False,
    dsrdtr=False
)

try:
    ser_tx.reset_output_buffer()
    ser_rx.reset_input_buffer()
    time.sleep(0.1)

    print(f"Starting Receive Test: {TX_PORT} (RS485 TX) -> {RX_PORT} (MAX485 RO)\n" + "-"*60)

    for i, payload in enumerate(test_payloads, 1):
        print(f"Test {i}: Sending -> {payload}")
        ser_tx.write(payload)
        ser_tx.flush()

        time.sleep(0.05)

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