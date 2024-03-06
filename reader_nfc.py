from time import sleep, time

import RPi.GPIO as GPIO  # type: ignore
from mfrc522 import SimpleMFRC522  # type: ignore

# delay between reads for the same card
DELAY = 1

reader = SimpleMFRC522()

# TODO: when refreshing the database from the sheet, clear the timestamps (otherwise this will fill up & take a lot of memory)
# maintain the last scanned time for each card id so that we can prevent multiple scans within a short time
timestamps = {}


def read_card():
    try:
        id, _ = reader.read()
        id = hex(id)[2:-2]
        if id in timestamps and time() - timestamps[id] < DELAY:
            return False
        timestamps[id] = time()
        return id
    except KeyboardInterrupt:
        raise
    except:
        return None


def close():
    GPIO.cleanup()


if __name__ == "__main__":
    try:
        while True:
            print("Hold a tag near the reader")
            print(read_card())
    except KeyboardInterrupt:
        close()
        raise
