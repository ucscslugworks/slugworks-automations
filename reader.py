import sys
from time import sleep

import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522

reader = SimpleMFRC522()

try:
    while True:
        print("Hold a tag near the reader")
        id = reader.read_id()
        print("ID: %s\nText: %s" % (id, text))
        sleep(5)
except KeyboardInterrupt:
    GPIO.cleanup()
    raise
