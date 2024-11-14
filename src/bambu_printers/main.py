import time
from collections import defaultdict
from datetime import datetime

from src import constants
from src.bambu_printers import get_account, get_db, get_printer, get_start_form
from src.log import setup_logs

logger = setup_logs("bambu_main")

account = get_account()
db = get_db()
sf = get_start_form()

devices = account.get_devices()
printers = dict()

for name in devices:
    printers[name] = get_printer(name, devices[name])

try:
    # main loop
    while True:
        try:
            time.sleep(constants.BAMBU_DELAY)
            logger.info("main: Running main loop")
            # Get the latest rows from the start form
            rows = sf.get()

            # if nothing was returned (possibly because an error occurred) set to empty list
            if not rows:
                rows = []

            for form_row in rows:
                # if the form is not already in the db, add it
                if not db.form_exists(form_row[0]):
                    db.add_form(form_row[0], form_row[1], form_row[3], form_row[2])

            # Get the latest tasks from the account
            tasks = account.get_tasks()

            if not tasks:
                tasks = []

            logger.info(f"main: {len(tasks)} tasks found")
            for task in tasks:
                if not task["isPrintable"] or db.print_exists(task["id"]):
                    continue

                start_time = datetime.fromisoformat(task["startTime"]).timestamp()
                end_time = start_time + task["costTime"]
                ams = task["amsDetailMapping"]
                colors = []
                for c in ams:
                    colors.append([c["sourceColor"], c["weight"]])
                for i in range(4 - len(colors)):
                    colors.append(["", 0])

                db.add_print(
                    task["id"],
                    task["deviceName"],
                    f"{task["designTitle"]} {task["title"]}",
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
            old_form_rows = dict()

            logger.info("main: Checking unmatched form responses for expiry")
            for u_form in db.get_unmatched_forms():
                if timestamp > u_form[1] + constants.BAMBU_TIMEOUT:
                    # db.expire_form(u_form[0])
                    old_form_rows[u_form[0]] = (u_form[2], u_form[3], u_form[1])
                else:
                    # Store the form in a dictionary with the printer name as the key and (form row, cruzid) as the value
                    form_printer_rows[u_form[2]] = (u_form[0], u_form[3])

            logger.info("main: Checking unmatched prints for expiry/matching")
            for u_print in db.get_unmatched_prints():
                if timestamp > u_print[4] + constants.BAMBU_TIMEOUT:
                    matched = False
                    for form_row in old_form_rows:
                        name, cruzid, form_time = old_form_rows[form_row]
                        if abs(form_time - u_print[4]) <= constants.BAMBU_TIMEOUT:
                            db.match(u_print[0], form_row)
                            matched = True
                            old_form_rows[form_row] = None

                    if not matched:
                        db.expire_print(u_print[0])
                        if (
                            u_print[5] > timestamp
                            and abs(u_print[4] - printers[u_print[1]].start_time) > 60
                        ):
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

            for form_row in old_form_rows:
                if old_form_rows[form_row] is not None:
                    db.expire_form(form_row)

            logger.info("main: Checking current prints for status changes")
            current_prints = defaultdict(list)
            for c_print in db.get_current_prints():
                if c_print[6] <= timestamp - 60:
                    # if print start time is more than 60 seconds ago

                    printer = printers[c_print[3]]

                    if abs(c_print[6] - printer.start_time) > 60:
                        if c_print[7] > timestamp:
                            db.archive_print(c_print[0], constants.PRINT_CANCELED)
                            db.subtract_limit(c_print[2], -1 * c_print[8])
                        else:
                            db.archive_print(c_print[0], constants.PRINT_SUCCEEDED)
                    elif printer.get_status() == constants.BAMBU_FINISH:
                        db.archive_print(c_print[0], constants.PRINT_SUCCEEDED)
                    elif printer.get_status() == constants.BAMBU_FAILED:
                        db.archive_print(c_print[0], constants.PRINT_FAILED)
                        db.subtract_limit(c_print[2], -1 * c_print[8])
                    elif printer.get_status() == constants.BAMBU_IDLE:
                        db.archive_print(c_print[0], constants.PRINT_CANCELED)
                        db.subtract_limit(c_print[2], -1 * c_print[8])
                    else:
                        current_prints[c_print[3]].append((c_print[0], c_print[7]))

            for name in current_prints:
                while len(current_prints[name]) > 1:
                    id, end_time = current_prints[name].pop(0)
                    if end_time < timestamp:
                        db.archive_print(id, constants.PRINT_SUCCEEDED)
                    else:
                        db.archive_print(id, constants.PRINT_CANCELED)

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
