import serial
import time

PORT = "COM10"  # Adjust if port re-enumerated after re-plugging
BAUDRATE = 9600
SAMPLES = 30

records = []

ser = serial.Serial(
    port=PORT,
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
    ser.reset_input_buffer()
    print(f"Sampling {SAMPLES} GGA sentences from {PORT}...")
    
    while len(records) < SAMPLES:
        line = ser.readline().decode('latin1', errors='replace').strip()
        if line.startswith('$GNGGA') or line.startswith('$GPGGA'):
            parts = line.split(',')
            if len(parts) > 9 and parts[6] in ('1', '2'):
                records.append({
                    'time': parts[1],
                    'lat': parts[2] + parts[3],
                    'lon': parts[4] + parts[5],
                    'sats': int(parts[7]),
                    'hdop': float(parts[8]),
                    'alt': float(parts[9]),
                    'system_time': time.time()
                })
                print(f"Sample {len(records)}/{SAMPLES}: Sats={parts[7]}, HDOP={parts[8]}, Lat={parts[2]}{parts[3]}, Lon={parts[4]}{parts[5]}")

    intervals = [records[i]['system_time'] - records[i-1]['system_time'] for i in range(1, len(records))]
    avg_interval = sum(intervals) / len(intervals) if intervals else 0

    print(f"\nAverage Update Interval: {avg_interval:.2f}s (~{1/avg_interval if avg_interval else 0:.2f} Hz)")

finally:
    if ser.is_open:
        ser.close()
        print("Port closed cleanly.")