from time import sleep, time
from multiprocessing import Queue, Process

import RPi.GPIO as GPIO  # type: ignore
from mfrc522 import SimpleMFRC522  # type: ignore

# https://github.com/pimylifeup/MFRC522-python
# https://www.nxp.com/docs/en/data-sheet/MFRC522.pdf

# delay between reads for the same card
DELAY = 1

# initialize the NFC reader object and GPIO pins (pins by the library)
reader = SimpleMFRC522()


def read_card():
    """
    read a card and return its id, or None if there was an error, or False if the card was scanned too soon
    """
    try:
        # read uid and any data on the card (not used)
        # this function will block until a card is read
        id, _ = reader.read()
        # convert the id to a hex string, remove the '0x' prefix, and remove the last 2 characters - extra data from the library?
        id = hex(id)[2:-2]
        return id.upper()
    except:
        # if there was an error, return None
        return None


def read_card_queue(q):
    try:
        q.put(read_card())
    except:
        q.put(None)


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
            return None

        val = q.get()

        if val is None:
            return False

        return val.upper()
    except:
        return False


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
