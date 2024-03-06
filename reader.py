import sys
from time import sleep, time

import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522

reader = SimpleMFRC522()

timestamps = {}


def read_card():
    try:
        id, _ = reader.read()
        id = hex(id)[2:-2]
        if id in timestamps and time() - timestamps[id] < 5:
            return False
        timestamps[id] = time()
    except KeyboardInterrupt:
        raise
    except:
        return None


try:
    while True:
        print("Hold a tag near the reader")
        # id, text = reader.read()
        # print("ID: %s\nText: %s" % (id, text))
        # sleep(5)
        print(read_card())
except KeyboardInterrupt:
    GPIO.cleanup()
    raise
