from arduino.app_utils import *
import json
import time

def loop():
    raw_response = Bridge.call("get_soil_data")
    
    try:
        data = json.loads(raw_response)
        if "error" in data:
            print(f"[ERROR] Sensor read issue: {data['error']}")
        else:
            print(f"T: {data['temp']}°C | M: {data['moisture']}% | pH: {data['ph']} | EC: {data['ec']} µS/cm | NPK: {data['n']}-{data['p']}-{data['k']}")
    except json.JSONDecodeError:
        print(f"[WARN] Invalid bridge frame: {raw_response}")
        
    time.sleep(2)

App.run(user_loop=loop)