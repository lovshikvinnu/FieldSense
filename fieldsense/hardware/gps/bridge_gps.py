import socket
from typing import Dict, Any, Optional
from ..models import GPSPosition, HardwareError, HardwareErrorCode

class BridgeGPSAdapter:
    """Reads NEO-M8N GPS telemetry via local TCP gateway."""
    
    def __init__(self, host: str = '127.0.0.1', port: int = 9876, timeout: float = 1.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def _parse_nmea_coord(self, coord_str: str) -> float:
        """Converts NMEA DDMM.MMMM[N/S/E/W] to Decimal Degrees."""
        try:
            direction = coord_str[-1]
            val = float(coord_str[:-1])
            degrees = int(val // 100)
            minutes = val % 100
            decimal = degrees + (minutes / 60.0)
            return -decimal if direction in ['S', 'W'] else decimal
        except Exception:
            raise ValueError("Failed to parse NMEA coordinate string")

    def read(self) -> GPSPosition:
        """Connects to the local App Lab gateway and fetches the latest telemetry."""
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                data = sock.recv(1024).decode('utf-8').strip()
        except socket.timeout:
            raise HardwareError(HardwareErrorCode.DEVICE_UNAVAILABLE, "GPS Gateway socket timeout (1s)")
        except ConnectionRefusedError:
            raise HardwareError(HardwareErrorCode.DEVICE_UNAVAILABLE, "GPS Gateway connection refused (is main.py running?)")
        except Exception as e:
            raise HardwareError(HardwareErrorCode.DEVICE_UNAVAILABLE, f"GPS Gateway connection error: {e}")

        if not data:
            raise HardwareError(HardwareErrorCode.MALFORMED_RESPONSE, "Empty response from GPS Gateway")

        parts = data.split(',')
        
        if parts[0] == "NO_FIX":
            return GPSPosition(latitude=0.0, longitude=0.0, fix_valid=False)
            
        if parts[0] == "FIX_OK" and len(parts) >= 5:
            try:
                lat = self._parse_nmea_coord(parts[1])
                lon = self._parse_nmea_coord(parts[2])
                sats = int(parts[3].split(':')[1])
                hdop = float(parts[4].split(':')[1])
                
                return GPSPosition(
                    latitude=lat,
                    longitude=lon,
                    fix_valid=True,
                    quality={"satellites": sats, "hdop": hdop}
                )
            except Exception as e:
                raise HardwareError(HardwareErrorCode.MALFORMED_RESPONSE, f"Failed to parse FIX_OK telemetry: {e}")
                
        raise HardwareError(HardwareErrorCode.MALFORMED_RESPONSE, f"Unrecognized telemetry format: {data}")