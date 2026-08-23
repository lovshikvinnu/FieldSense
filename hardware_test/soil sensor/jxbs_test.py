import serial
import time


PORT = "COM8"
BAUD = 9600


def modbus_crc(data):
    crc = 0xFFFF

    for byte in data:
        crc ^= byte

        for _ in range(8):
            if crc & 1:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1

    return crc


def make_request(register):
    frame = bytes([
        0x01,                       # Slave ID
        0x03,                       # Function: Read Holding Registers
        (register >> 8) & 0xFF,    # Register high byte
        register & 0xFF,            # Register low byte
        0x00,                       # Quantity high byte
        0x01                        # Quantity low byte
    ])

    crc = modbus_crc(frame)

    return frame + bytes([
        crc & 0xFF,                 # CRC low byte
        (crc >> 8) & 0xFF          # CRC high byte
    ])


def check_crc(response):
    if len(response) != 7:
        return False

    received_crc = response[-2] | (response[-1] << 8)
    calculated_crc = modbus_crc(response[:-2])

    return received_crc == calculated_crc


def read_register(ser, name, register, scale, unit):

    request = make_request(register)

    print("\n--------------------------------")
    print(name)
    print(f"Register: 0x{register:04X}")
    print("Request:", request.hex(" ").upper())

    # Clear anything left in the receive buffer
    ser.reset_input_buffer()

    # Send request
    ser.write(request)
    ser.flush()

    # One register response:
    # ID + Function + Byte Count + 2 data bytes + 2 CRC = 7 bytes
    response = ser.read(7)

    print("Response:", response.hex(" ").upper())
    print("Bytes:", len(response))

    if len(response) != 7:
        print("❌ INVALID RESPONSE LENGTH")
        return None

    if not check_crc(response):
        print("❌ CRC FAILED")
        return None

    print("✅ CRC PASS")

    # Response format:
    #
    # Byte 0 = Slave ID
    # Byte 1 = Function
    # Byte 2 = Byte count
    # Byte 3 = Data high
    # Byte 4 = Data low
    # Byte 5 = CRC low
    # Byte 6 = CRC high

    raw = (response[3] << 8) | response[4]

    value = raw / scale

    print(f"Raw value: {raw}")
    print(f"Decoded: {value} {unit}")

    return value


# ============================================================
# MAIN
# ============================================================

with serial.Serial(
    port=PORT,
    baudrate=BAUD,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=1
) as ser:

    print("JXBS 7-IN-1 REGISTER TEST")
    print("==========================")
    print("Port:", PORT)
    print("Baud:", BAUD)

    # --------------------------------------------------------
    # 1. pH
    # Register 0x0006
    # Scaling: raw / 100
    # --------------------------------------------------------

    read_register(
        ser,
        "pH",
        0x0006,
        100,
        "pH"
    )

    time.sleep(0.2)


    # --------------------------------------------------------
    # 2. Moisture
    # Register 0x0012
    # Scaling: raw / 10
    # --------------------------------------------------------

    read_register(
        ser,
        "Moisture",
        0x0012,
        10,
        "%RH"
    )

    time.sleep(0.2)


    # --------------------------------------------------------
    # 3. Temperature
    # Register 0x0013
    # Scaling: raw / 10
    # --------------------------------------------------------

    read_register(
        ser,
        "Temperature",
        0x0013,
        10,
        "°C"
    )

    time.sleep(0.2)


    # --------------------------------------------------------
    # 4. EC / Conductivity
    # Register 0x0015
    # Scaling: raw / 1
    # --------------------------------------------------------

    read_register(
        ser,
        "EC / Conductivity",
        0x0015,
        1,
        "µS/cm"
    )

    time.sleep(0.2)


    # --------------------------------------------------------
    # 5. Nitrogen
    # Register 0x001E
    # Scaling: raw / 1
    # --------------------------------------------------------

    read_register(
        ser,
        "Nitrogen",
        0x001E,
        1,
        "mg/kg"
    )

    time.sleep(0.2)


    # --------------------------------------------------------
    # 6. Phosphorus
    # Register 0x001F
    # Scaling: raw / 1
    # --------------------------------------------------------

    read_register(
        ser,
        "Phosphorus",
        0x001F,
        1,
        "mg/kg"
    )

    time.sleep(0.2)


    # --------------------------------------------------------
    # 7. Potassium
    # Register 0x0020
    # Scaling: raw / 1
    # --------------------------------------------------------

    read_register(
        ser,
        "Potassium",
        0x0020,
        1,
        "mg/kg"
    )