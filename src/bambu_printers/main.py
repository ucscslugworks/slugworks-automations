import time

from src import constants
from src.bambu_printers import BambuAccount, BambuDB, Printer, StartForm
from src.log import setup_logs

logger = setup_logs("bambu_main")

account = BambuAccount("slugworks@ucsc.edu")
db = BambuDB()
form = StartForm()

devices = account.get_devices()
printers = dict()

for name in devices:
    printers[name] = Printer(account, name, devices[name])

try:
    while True:
        try:
            time.sleep(constants.BAMBU_DELAY)
            logger.info("main: Running main loop")
            # Get the latest row from the start form
            rows = form.get()
            if not rows:
                rows = []

            for row in rows:
                if not db.form_exists(row[0]):
                    db.add_form(row[0], row[1], row[3], row[2])

            # Get the latest tasks from the account
            tasks = account.get_tasks()

            if not tasks:
                tasks = []

            logger.info(f"main: {len(tasks)} tasks found")
            for task in tasks:
                if not task["isPrintable"] or db.print_exists(task["id"]):
                    continue

                start_time = time.mktime(
                    time.strptime(task["startTime"], "%Y-%m-%dT%H:%M:%S%z")
                ) - (time.timezone if not time.daylight else time.altzone)
                end_time = time.mktime(
                    time.strptime(task["endTime"], "%Y-%m-%dT%H:%M:%S%z")
                ) - (time.timezone if not time.daylight else time.altzone)
                ams = task["amsDetailMapping"]
                colors = []
                for c in ams:
                    colors.append([c["sourceColor"], c["weight"]])
                for i in range(4 - len(colors)):
                    colors.append(["", 0])

                db.add_print(
                    task["id"],
                    task["deviceName"],
                    task["title"],
                    task["cover"],
                    int(start_time),
                    int(end_time),
                    task["weight"],
                    colors[0][0],
                    colors[0][1],
                    colors[1][0],
                    colors[1][1],
                    colors[2][0],
                    colors[2][1],
                    colors[3][0],
                    colors[3][1],
                )

            timestamp = int(time.time())

            form_printer_rows = dict()

            logger.info("main: Checking unmatched form responses for expiry")
            for u_form in db.get_unmatched_forms():
                if timestamp > u_form[1] + constants.BAMBU_TIMEOUT:
                    db.expire_form(u_form[0])
                else:
                    # Store the form in a dictionary with the printer name as the key and (form row, cruzid) as the value
                    form_printer_rows[u_form[2]] = (u_form[0], u_form[3])

            logger.info("main: Checking unmatched prints for expiry/matching")
            for u_print in db.get_unmatched_prints():
                if timestamp > u_print[4] + constants.BAMBU_TIMEOUT:
                    db.expire_print(u_print[0])
                    if u_print[5] > timestamp:
                        printers[u_print[1]].cancel()
                elif u_print[1] in form_printer_rows:
                    form_row, cruzid = form_printer_rows[u_print[1]]

                    db.match(u_print[0], form_row)
                    del form_printer_rows[u_print[1]]

                    if db.get_limit(cruzid) < u_print[6]:
                        printers[u_print[1]].cancel()
                        db.archive_print(u_print[0], constants.PRINT_CANCELED)
                    else:
                        db.subtract_limit(cruzid, u_print[6])

            logger.info("main: Checking current prints for status changes")
            for c_print in db.get_current_prints():
                if c_print[6] + 60 > timestamp:
                    # if print start time is not more than 60 seconds ago, skip
                    continue

                printer = printers[c_print[1]]
                if printer.get_status() == constants.BAMBU_FINISH:
                    db.archive_print(c_print[0], constants.PRINT_SUCCEEDED)
                elif printer.get_status() == constants.BAMBU_FAILED:
                    db.archive_print(c_print[0], constants.PRINT_FAILED)
                    db.subtract_limit(c_print[2], -1 * c_print[8])
                elif printer.get_status() == constants.BAMBU_IDLE:
                    db.archive_print(c_print[0], constants.PRINT_CANCELED)
                    db.subtract_limit(c_print[2], -1 * c_print[8])

            logger.info("main: Finished main loop")
        except Exception as e:
            logger.error(f"main: {type(e)} {e}")

            if type(e) == KeyboardInterrupt:
                raise e

except KeyboardInterrupt:
    logger.warning("main: Keyboard interrupt (may up to 60 seconds to stop)")
    for name in printers:
        logger.info(f"main: Stopping printer {name}")
        printers[name].stop_thread()
    logger.info("main: Stopping account refresh thread")
    account.stop_refresh_thread()
    exit(0)
except Exception as e:
    logger.error(f"main: {type(e)} {e}")
    exit(1)
