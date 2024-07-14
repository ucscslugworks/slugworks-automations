import logging
import os
from datetime import datetime, timedelta
from threading import Thread
from time import sleep, time

import board  # type: ignore
import neopixel  # type: ignore

try:
    import RPi.GPIO as GPIO  # type: ignore
except RuntimeError:
    print(
        "Error importing RPi.GPIO!  This is probably because you need superuser privileges.  You can achieve this by using 'sudo' to run your script"
    )

from .. import sheet
from ..nfc import nfc_reader as nfc

# Change directory to current file location
path = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
os.chdir(path)

# Create a new directory for logs if it doesn't exist
if not os.path.exists(path + "/logs/reader"):
    os.makedirs(path + "/logs/reader")

# create new logger with all levels
logger = logging.getLogger("root")
logger.setLevel(logging.DEBUG)

# create file handler which logs debug messages (and above - everything)
fh = logging.FileHandler(f"logs/reader/{str(datetime.now())}.log")
fh.setLevel(logging.DEBUG)

# create console handler which only logs warnings (and above)
ch = logging.StreamHandler()
ch.setLevel(logging.WARNING)

# create formatter and add it to the handlers
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s: %(message)s")
fh.setFormatter(formatter)
ch.setFormatter(formatter)

# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)


SHEET_UPDATE_HOUR = 4  # pull new data from sheet at 4am
CHECKIN_TIMEOUT = 30  # check in every 30 seconds

SCAN_COLOR_HOLD = 2  # seconds to hold color after scan
BREATHE_DELAY = 0.05  # seconds to wait between LED brightness changes
BRIGHTNESS_LOW = 0.2  # low brightness while breathing LEDs
BRIGHTNESS_HIGH = 0.5  # high brightness while holding color

DOOR_SENSOR_PIN = 16  # GPIO pin for door sensor

breathe = True  # breathe LEDs when no card is scanned
scan_time = None  # time of last scan to hold color
EXIT = False  # exit flag
alarm_status = False  # True if alarm is triggered - reported back to sheet
door_open = False  # True if door is open
door_change_time = time()  # time of last door state change
door_time_limit = 0  # time limit for door open before alarm based on card scan

num_pixels = 30  # 30 LEDs
pixel_pin = board.D18  # LEDs are on GPIO pin 18
ORDER = neopixel.GRB  # RGB color order
pixels = neopixel.NeoPixel(
    pixel_pin,
    num_pixels,
    brightness=BRIGHTNESS_LOW,
    auto_write=False,
    pixel_order=ORDER,
)  # initialize LEDs
GPIO.setmode(GPIO.BCM)  # set GPIO mode to BCM (GPIO numbering)


# thread to breathe LEDs in background
def breathe_leds():
    global breathe, scan_time, EXIT
    # try except for clean exit on keyboard interrupt
    try:
        # time of last brightness change
        last_change_time = 0

        # loop until exit flag is set
        while not EXIT:
            # try except to handle errors and continue
            try:
                # if breathe flag is set (no card scanned)
                if breathe:
                    # increase "brightness" in steps of 5
                    for i in range(0, 255, 5):
                        # wait for BREATHE_DELAY seconds
                        while time() - last_change_time < BREATHE_DELAY:
                            # if breathe flag is unset, break loop
                            if not breathe:
                                break

                        # if breathe flag is unset, break loop
                        if not breathe:
                            break

                        # update last change time
                        last_change_time = time()

                        # set all LEDs to i (gradient from black to white)
                        pixels.fill((i, i, i))

                        # write pixel values to LEDs
                        pixels.show()

                    # decrease "brightness" in steps of 5
                    for i in range(255, 0, -5):
                        # wait for BREATHE_DELAY seconds
                        while time() - last_change_time < BREATHE_DELAY:
                            # if breathe flag is unset, break loop
                            if not breathe:
                                break

                        # if breathe flag is unset, break loop
                        if not breathe:
                            break

                        # update last change time
                        last_change_time = time()

                        # set all LEDs to i (gradient from white to black)
                        pixels.fill((i, i, i))

                        # write pixel values to LEDs
                        pixels.show()
                elif scan_time and datetime.now() - scan_time > timedelta(
                    0, SCAN_COLOR_HOLD, 0, 0, 0, 0, 0
                ):  # if scan time is set (a card was scanned) and SCAN_COLOR_HOLD seconds have passed

                    # reenable breathe flag
                    breathe = True

                    # clear scan time
                    scan_time = None

                    # set LED brightness back to low
                    pixels.brightness = BRIGHTNESS_LOW
            except Exception as e:  # catch any exceptions
                # if exception is KeyboardInterrupt, raise it to exit cleanly
                if type(e) == KeyboardInterrupt:
                    raise e
                # otherwise, print error and sleep for 60 seconds to prevent spamming
                logger.error(f"Error: {e}")
                sleep(60)
    except KeyboardInterrupt:
        # set exit flag to True - this will exit the main loop and cause the end of this thread
        EXIT = True


if __name__ == "__main__":
    # try except for red error LED on exception
    try:
        # get sheet data and check in
        sheet.get_sheet_data(limited=True)
        sheet.check_in(alarm_status=alarm_status)

        # start breathe LEDs thread
        Thread(target=breathe_leds).start()
    except Exception as e:
        # print error, set red LEDs, sleep for 5 seconds, and set exit flag
        logger.error(e)
        pixels.fill((255, 0, 0))
        pixels.show()
        sleep(5)
        EXIT = True

    GPIO.setup(DOOR_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # try except for clean exit on keyboard interrupt
    try:
        # list of last 5 card IDs scanned - debouncing to prevent multiple scans
        last_ids = [None] * 5

        # loop until exit flag is set
        while not EXIT:
            # try except to handle errors and continue
            try:
                # if sheet has never been updated or sheet data is older than today and it is past SHEET_UPDATE_HOUR
                if (
                    not sheet.last_update_time
                    or datetime.now().date() > sheet.last_update_time.date()
                ) and datetime.now().hour >= SHEET_UPDATE_HOUR:
                    # update sheet data and check in
                    logger.info("Updating sheet...")
                    sheet.get_sheet_data()
                    sheet.check_in(alarm_status=alarm_status)
                elif not sheet.last_checkin_time or datetime.now() - sheet.last_checkin_time > timedelta(
                    0, CHECKIN_TIMEOUT, 0, 0, 0, 0, 0
                ):  # if last checkin time is not set or it has been CHECKIN_TIMEOUT seconds since last checkin
                    # check in
                    logger.info("Checking in...")
                    sheet.check_in(alarm_status=alarm_status)

                # read card ID from NFC reader with a timeout of 1 second
                # print("Hold a tag near the reader")
                card_id = nfc.read_card_queue_timeout(1)
                print(card_id)
                # if card ID is not None and it is not in the last 5 IDs scanned - a new card has been scanned
                if card_id and card_id not in last_ids:
                    # add card ID to last IDs scanned and remove the oldest one
                    last_ids.append(card_id)
                    last_ids.pop(0)

                    # scan card ID in sheet - returns color and alarm timeout
                    response = sheet.scan_uid(card_id)

                    # if response is not a color/alarm timeout tuple
                    if not response:
                        # print an error - likely caused by the card being in the database but not having a color for this room
                        logger.error("error - card not in database or something else")
                        # TODO: flash no access color or some other unique indication
                        pass
                    else:  # a response was received
                        # unpack color and timeout from response
                        color, timeout = response

                        # print color and timeout for debugging
                        print(color, timeout)

                        # convert color from hex to RGB tuple
                        colors = tuple(
                            [int(color[i : i + 2], 16) for i in range(0, len(color), 2)]
                        )

                        # print colors for debugging
                        # print(colors)

                        # stop breathing LEDs, set scan time, and sleep to give the breathing thread time to stop
                        breathe = False
                        scan_time = datetime.now()
                        sleep(BREATHE_DELAY * 2)

                        # set LED brightness to high, fill LEDs with color, and show LEDs
                        pixels.brightness = BRIGHTNESS_HIGH
                        pixels.fill(colors)
                        pixels.show()

                        if alarm_status and timeout:
                            alarm_status = False
                            sheet.check_in(alarm_status=alarm_status)
                            print("Alarm untriggered")
                            door_change_time = time()
                            door_time_limit = timeout * 60

                elif card_id is None:  # scanned too soon or no card scanned
                    # add None to last IDs scanned and remove the oldest one (if we didn't do this, the same person could never scan twice in a row, even if they waited a long time)
                    last_ids.append(None)
                    last_ids.pop(0)
                elif card_id is False:  # some error occurred, exit loop
                    EXIT = True

                # check if door sensor is open
                input_state = bool(GPIO.input(DOOR_SENSOR_PIN))
                if input_state != door_open and time() - door_change_time > 0.5:
                    door_open = input_state
                    door_change_time = time()

                    if not door_open and alarm_status:
                        alarm_status = False
                        sheet.check_in(alarm_status=alarm_status)
                        print("Alarm untriggered")

                if (
                    door_open
                    and not alarm_status
                    and time() - door_change_time > door_time_limit
                    and time() - door_change_time
                    > sheet.this_reader["alarm_delay_min"] * 60
                ):
                    alarm_status = True
                    sheet.check_in(alarm_status=alarm_status)
                    print("Alarm triggered")

            except Exception as e:  # catch any exceptions
                # if exception is KeyboardInterrupt, raise it to exit cleanly
                if type(e) == KeyboardInterrupt:
                    raise e

                # otherwise, print error and sleep for 60 seconds to prevent spamming
                logger.error(f"Error: {e}")
                sleep(60)

    except KeyboardInterrupt:  # if KeyboardInterrupt is raised, set exit flag to True
        EXIT = True

    # if here, exit flag is set so breathing should stop
    if breathe:
        breathe = False

    # wait until breathing thread has stopped
    sleep(BREATHE_DELAY * 2)

    # set LEDs to black and show them - this is the "off" state
    pixels.fill((0, 0, 0))
    pixels.show()

    # close NFC reader - needed to prevent errors on next run
    nfc.close()
