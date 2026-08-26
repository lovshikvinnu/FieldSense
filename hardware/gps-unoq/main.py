import time
from arduino.app_utils import *

def loop():
    # Fetch the latest parsed GPS string from the STM32 via the Bridge
    gps_data_str = Bridge.call("get_gps_data")
    
    # Print the clean output to the terminal
    print(f"[GPS TELEMETRY] | {gps_data_str}")
    
    # Main loop interval
    time.sleep(1) 

App.run(user_loop=loop)