try:
    import RPi.GPIO as GPIO  # type: ignore
except RuntimeError:
    print(
        "Error importing RPi.GPIO!  This is probably because you need superuser privileges.  You can achieve this by using 'sudo' to run your script"
    )

GPIO.setmode(GPIO.BCM)

GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)

old_input_state = False

while True:
    input_state = bool(GPIO.input(16))
    if input_state != old_input_state:
        print(input_state)
        old_input_state = input_state