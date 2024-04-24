from time import sleep, time
from multiprocessing import Queue, Process

import RPi.GPIO as GPIO  # type: ignore
from mfrc522 import SimpleMFRC522  # type: ignore

# delay between reads for the same card
DELAY = 1

reader = SimpleMFRC522()

# TODO: when refreshing the database from the sheet, clear the timestamps (otherwise this will fill up & take a lot of memory)
# maintain the last scanned time for each card id so that we can prevent multiple scans within a short time
# timestamps = {}


def read_card():
    """
    read a card and return its id, or None if there was an error, or False if the card was scanned too soon
    """
    try:
        id, _ = reader.read()
        print("Card read: ", id)
        id = hex(id)[2:-2]
        return id
    except:
        raise


def read_card_queue(q):
    try:
        q.put(read_card())
    except:
        raise


def read_card_queue_timeout(time):
    """
    Call read_card() with a timeout

    time: float: the time limit in seconds

    Returns None if there was an error, or passes through the return value of read_card()
    """
    try:
        q = Queue()
        p = Process(target=read_card_queue, args=(q,))
        p.start()
        p.join(time)
        if p.is_alive():
            p.terminate()
            print("timeout")
            return None

        return q.get().upper()
    except:
        raise


def close():
    """clean up the GPIO pins"""
    GPIO.cleanup()


if __name__ == "__main__":
    try:
        while True:
            print("Hold a tag near the reader")
            print(read_card())
    except KeyboardInterrupt:
        close()
        raise
