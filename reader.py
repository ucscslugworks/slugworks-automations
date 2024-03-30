from datetime import datetime, timedelta
from multiprocessing import Process, Queue
from threading import Thread
from time import sleep

import board
import neopixel

import reader_nfc as nfc
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
BREATHE_DELAY = 0.02  # seconds


def breathe_leds():
    global breathe, scan_time
    try:
        while True:
            if breathe:
                for i in range(0, 255, 5):
                    if not breathe:
                        break
                    pixels.fill((i, i, i))
                    pixels.show()
                    sleep(BREATHE_DELAY)
                for i in range(255, 0, -5):
                    if not breathe:
                        break
                    pixels.fill((i, i, i))
                    pixels.show()
                    sleep(BREATHE_DELAY)
            elif scan_time and datetime.now() - scan_time > timedelta(
                0, SCAN_COLOR_HOLD, 0, 0, 0, 0, 0
            ):
                breathe = True
                scan_time = None
                pixels.brightness = 0.2
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sheet.get_sheet_data(limited=True)
    sheet.check_in(alarm_status=alarm_status)
    Thread(target=breathe_leds).start()
    try:
        while True:
            if (
                not sheet.last_update_date
                or datetime.now().date() > sheet.last_update_date
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
            card_id = nfc.read_card_queue_timeout(10)
            print(card_id)
            if card_id:
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
                    sleep(BREATHE_DELAY)
                    pixels.brightness = 0.5
                    pixels.fill(colors)
                    pixels.show()
            else:
                print("error - scanned too soon or not scanned")

    except KeyboardInterrupt:
        nfc.close()
        if breathe:
            breathe = False
            sleep(BREATHE_DELAY)
        pixels.fill((0, 0, 0))
        pixels.show()
        pass
