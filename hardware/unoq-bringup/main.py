from arduino.app_utils import *
import time

def loop():
    status = Bridge.call("get_uart_status")
    print(f"UART Loopback: {status}")
    time.sleep(1)

App.run(user_loop=loop)