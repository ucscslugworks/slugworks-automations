import os
from time import sleep, time

import nfc
from src import api, constants, log

# import nfc_fake as nfc

# Change directory to repository root
path = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
os.chdir(path)

# Create a new logger for the reader module
logger = log.setup_logs("desk", log.INFO)

# pass logger to api
api.set_logger(logger)

scan_time = 0

if __name__ == "__main__":
    try:
        while True:
            try:
                uid = nfc.read_card()
                if uid:
                    scan_time = time()
                    api.desk_uid_scan(uid)
                elif time() - scan_time > 30:
                    api.desk_uid_scan("")
            except Exception as e:  # catch any exceptions
                # if exception is KeyboardInterrupt, raise it to exit cleanly
                if type(e) == KeyboardInterrupt:
                    raise e

                # otherwise, print error and sleep for 60 seconds to prevent spamming
                logger.error(f"Error: {e}")
                sleep(60)
    except KeyboardInterrupt:
        logger.info("Exiting...")
        exit(0)
