import time

try:
    import RPi.GPIO as GPIO  # type: ignore
except RuntimeError:
    print(
        "Error importing RPi.GPIO!  This is probably because you need superuser privileges.  You can achieve this by using 'sudo' to run your script"
    )

GPIO.setmode(GPIO.BCM)

GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)

door_open = True
last_change = time.time()

while True:
    input_state = bool(GPIO.input(16))
    if input_state != door_open and time.time() - last_change > 0.1:
        print(input_state)
        door_open = input_state
        last_change = time.time()

    if door_open and time.time() - last_change > 5:
        print("Door has been open for 5+ seconds")
