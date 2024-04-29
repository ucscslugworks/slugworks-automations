from datetime import datetime, timedelta
from multiprocessing import Process, Queue
from threading import Thread
from time import sleep, time

import board  # type: ignore
import neopixel  # type: ignore

import nfc_reader as nfc
import sheet

SHEET_UPDATE_HOUR = 4  # 4am
CHECKIN_TIMEOUT = 30  # 30 seconds

alarm_status = False

num_pixels = 30  # 30 LEDs
pixel_pin = board.D18  # GPIO pin 18
ORDER = neopixel.GRB  # RGB color order
pixels = neopixel.NeoPixel(
    pixel_pin, num_pixels, brightness=0.2, auto_write=False, pixel_order=ORDER
)

breathe = True
scan_time = None
SCAN_COLOR_HOLD = 2  # seconds
BREATHE_DELAY = 0.05  # seconds
EXIT = False


def breathe_leds():
    global breathe, scan_time, EXIT
    try:
        last_change_time = 0
        while not EXIT:
            if breathe:
                for i in range(0, 255, 5):
                    while time() - last_change_time < BREATHE_DELAY:
                        if not breathe:
                            break
                    if not breathe:
                        break
                    last_change_time = time()
                    pixels.fill((i, i, i))
                    pixels.show()
                for i in range(255, 0, -5):
                    while time() - last_change_time < BREATHE_DELAY:
                        if not breathe:
                            break
                    if not breathe:
                        break
                    last_change_time = time()
                    pixels.fill((i, i, i))
                    pixels.show()
            elif scan_time and datetime.now() - scan_time > timedelta(
                0, SCAN_COLOR_HOLD, 0, 0, 0, 0, 0
            ):
                breathe = True
                scan_time = None
                pixels.brightness = 0.2
    except KeyboardInterrupt:
        EXIT = True


if __name__ == "__main__":
    try:
        sheet.get_sheet_data(limited=True)
        sheet.check_in(alarm_status=alarm_status)
        Thread(target=breathe_leds).start()
    except Exception as e:
        print(e)
        pixels.fill((255, 0, 0))
        pixels.show()
        sleep(5)
        EXIT = True

    try:

        last_ids = [None] * 5

        while not EXIT:
            if (
                not sheet.last_update_time
                or datetime.now().date() > sheet.last_update_time.date()
            ) and datetime.now().hour >= SHEET_UPDATE_HOUR:
                print("Updating sheet...")
                sheet.get_sheet_data()
                sheet.check_in(alarm_status=alarm_status)
            elif (
                not sheet.last_checkin_time
                or datetime.now() - sheet.last_checkin_time
                > timedelta(0, CHECKIN_TIMEOUT, 0, 0, 0, 0, 0)
            ):
                print("Checking in...")
                sheet.check_in(alarm_status=alarm_status)

            print("Hold a tag near the reader")
            card_id = nfc.read_card_queue_timeout(1)
            print(card_id)
            if card_id and card_id not in last_ids:
                last_ids.append(card_id)
                last_ids.pop(0)
                response = sheet.scan_uid(card_id)
                if not response:
                    print("error - card not in database or something else")
                    # TODO: flash no access color
                    pass
                else:
                    color, timeout = response
                    print(color, timeout)
                    colors = tuple(
                        [int(color[i : i + 2], 16) for i in range(0, len(color), 2)]
                    )
                    print(colors)
                    breathe = False
                    scan_time = datetime.now()
                    sleep(BREATHE_DELAY * 2)
                    pixels.brightness = 0.5
                    pixels.fill(colors)
                    pixels.show()
            elif card_id is None:
                # print("error - scanned too soon or not scanned")
                last_ids.append(None)
                last_ids.pop(0)
            elif card_id is False:
                # False --> exception occurred
                EXIT = True

    except KeyboardInterrupt:
        EXIT = True

    if breathe:
        breathe = False

    sleep(BREATHE_DELAY * 2)

    pixels.fill((0, 0, 0))
    pixels.show()
    nfc.close()
