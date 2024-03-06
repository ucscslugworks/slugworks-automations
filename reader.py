import sys
from time import sleep

import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522

reader = SimpleMFRC522()

def read_card():
    try:
        id, _ = reader.read()
        return hex(id)[2:]
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
