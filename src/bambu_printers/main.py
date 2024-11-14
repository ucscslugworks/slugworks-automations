import time
import traceback
from collections import defaultdict
from datetime import datetime

from src import constants, log
from src.bambu_printers import get_account, get_db, get_printer, get_start_form

logger = log.setup_logs("bambu_main", additional_handlers=[("bambu", log.INFO)])

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
            # delay between loops - this is at the beginning in case of an exception - don't spam
            time.sleep(constants.BAMBU_DELAY)
            logger.info("main: Running main loop")

            # Get the latest rows from the start form
            rows = sf.get()

            # if nothing was returned (possibly because an error occurred) set to empty list
            if not rows:
                rows = []

            logger.info(f"main: {len(rows)} forms found")
            for form_row in rows:
                # if the form is not already in the db, add it
                if not db.form_exists(form_row[0]):
                    db.add_form(form_row[0], form_row[1], form_row[3], form_row[2])

            # Get the latest cloud tasks from the account
            tasks = account.get_tasks()

            # if nothing was returned (possibly because an error occurred) set to empty list
            if not tasks:
                tasks = []

            logger.info(f"main: {len(tasks)} tasks found")
            for task in tasks:
                if not task["isPrintable"] or db.print_exists(task["id"]):
                    # if the task is not a print or is already in the db, skip
                    continue

                # parse the start time and calculate the end time
                start_time = datetime.fromisoformat(task["startTime"]).timestamp()
                end_time = start_time + task["costTime"]

                # get the colors and per-color weights from the task
                ams = task["amsDetailMapping"]
                colors = []
                for c in ams:
                    colors.append([c["sourceColor"], c["weight"]])

                # pad the colors with empty strings and 0s to make sure there are 4
                # NOTE: if we ever support more than 4 colors, this will need to be updated (along with the db)
                for i in range(4 - len(colors)):
                    colors.append(["", 0])

                # add the print to the db
                db.add_print(
                    task["id"],  # print id
                    task["deviceName"],  # printer name
                    f"{task["designTitle"]} {task["title"]}",  # combine the design and task titles
                    task["cover"],  # link to cover image
                    int(start_time),  # start time
                    int(end_time),  # end time
                    task["weight"],  # total weight
                    colors[0][0],  # color 0 hex code
                    colors[0][1],  # color 0 weight
                    colors[1][0],  # color 1 hex code
                    colors[1][1],  # color 1 weight
                    colors[2][0],  # color 2 hex code
                    colors[2][1],  # color 2 weight
                    colors[3][0],  # color 3 hex code
                    colors[3][1],  # color 3 weight
                )

            # loop timestamp - ensure consistent time comparisons for all operations in this loop
            timestamp = int(time.time())

            # dict to store form rows and printer names (as submitted in form) for unmatched forms
            form_printer_rows = dict()

            # dict to store forms from before the timeout for matching with prints before the timeout
            # used if the program hasn't been run for a while and there are unmatched forms + prints that shouldn't be canceled
            old_form_rows = dict()

            logger.info("main: Checking unmatched form responses for expiry")
            for u_form in db.get_unmatched_forms():
                # iterate through all unmatched forms
                if timestamp > u_form[1] + constants.BAMBU_TIMEOUT:
                    # if the form was submitted more than 10 minutes ago (timeout), mark as old
                    # store the form in a dictionary with the form row as the key and (name, cruzid, form time) as the value
                    old_form_rows[u_form[0]] = (u_form[2], u_form[3], u_form[1])
                else:
                    # Store the form in a dictionary with the printer name as the key and (form row, cruzid) as the value
                    # newer forms for the same printer will overwrite older forms - only the most recent form is used
                    form_printer_rows[u_form[2]] = (u_form[0], u_form[3])
                    # also store the form in old_form_rows, in case they are within 10 minutes of the print (even if the print is older than 10 min)
                    old_form_rows[u_form[0]] = (u_form[2], u_form[3], u_form[1])

            logger.info("main: Checking unmatched prints for expiry/matching")
            for u_print in db.get_unmatched_prints():
                # iterate through all unmatched prints
                if timestamp > u_print[4] + constants.BAMBU_TIMEOUT:
                    # if the print was submitted more than 10 minutes ago (timeout), compare with old forms
                    matched = False  # flag to check if the print was matched
                    for form_row in reversed(old_form_rows):
                        # iterate through all old forms
                        if old_form_rows[form_row] is None:
                            # if the form has already been used, skip
                            continue

                        name, cruzid, form_time = old_form_rows[form_row]
                        if abs(form_time - u_print[4]) <= constants.BAMBU_TIMEOUT:
                            # if the form was submitted within 10 minutes of the print, match them
                            db.match(u_print[0], form_row)
                            matched = True
                            old_form_rows[form_row] = None  # mark the form as used
                            if (
                                name in form_printer_rows
                                and form_printer_rows[name][0] == form_row
                            ):
                                # if there has been no newer form for the same printer, remove the form from form_printer_rows so it doesn't get re-matched
                                del form_printer_rows[name]

                            break

                    if not matched:
                        # if the form was not matched, expire it
                        db.expire_print(u_print[0])
                        if abs(u_print[4] - printers[u_print[1]].start_time) <= 60:
                            # if the start time in the print task is within 60 seconds of the printer's current print's start time, they must be the same print
                            # cancel the print (no form was submitted/matched)
                            printers[u_print[1]].cancel()

                elif u_print[1] in form_printer_rows:
                    # if the print was submitted within the last 10 minutes and there is a form for the same printer
                    # get the form details
                    form_row, cruzid = form_printer_rows[u_print[1]]

                    # match the print with the form and remove the form from form_printer_rows
                    db.match(u_print[0], form_row)
                    del form_printer_rows[u_print[1]]

                    # check if the user has enough weight left in their limit
                    if db.get_limit(cruzid) < u_print[6]:
                        # if the user does not have enough weight left, cancel the print
                        printers[u_print[1]].cancel()
                        # archive the print as canceled
                        db.archive_print(u_print[0], constants.PRINT_CANCELED)
                    else:
                        # if the user has enough weight left, subtract the print weight from their limit
                        db.subtract_limit(cruzid, u_print[6])

            # expire any forms that were not matched and are older than 10 minutes
            for form_row in old_form_rows:
                # check if the form was used
                if old_form_rows[form_row] is not None:
                    db.expire_form(form_row)

            logger.info("main: Checking current prints for status changes")
            current_prints = defaultdict(
                list
            )  # dict to store current prints for each printer (in case there are multiple)

            # iterate through all current prints
            for c_print in db.get_current_prints():
                if c_print[6] <= timestamp - 60:
                    # if print start time is more than 60 seconds ago (ignore very recent prints in case the printer object status hasn't updated yet)

                    # get the printer object
                    printer = printers[c_print[3]]

                    if abs(c_print[6] - printer.start_time) > 60:
                        # if the start time in the print task is not within 60 seconds of the printer's current print's start time, they must not be the same print
                        if c_print[7] > timestamp:
                            # if the print's end time is in the future, the print probably was canceled
                            db.archive_print(c_print[0], constants.PRINT_CANCELED)
                            # add the print weight back to the user's limit
                            db.subtract_limit(c_print[2], -1 * c_print[8])
                        else:
                            # if the print's end time is in the past, the print probably succeeded
                            db.archive_print(c_print[0], constants.PRINT_SUCCEEDED)

                    elif printer.get_status() == constants.BAMBU_FINISH:
                        # if the printer status is finish, the print succeeded
                        db.archive_print(c_print[0], constants.PRINT_SUCCEEDED)

                    elif printer.get_status() == constants.BAMBU_FAILED:
                        # if the printer status is failed, the print failed
                        db.archive_print(c_print[0], constants.PRINT_FAILED)
                        # add the print weight back to the user's limit
                        db.subtract_limit(c_print[2], -1 * c_print[8])

                    elif printer.get_status() == constants.BAMBU_IDLE:
                        # if the printer status is idle, the print was canceled
                        db.archive_print(c_print[0], constants.PRINT_CANCELED)
                        # add the print weight back to the user's limit
                        db.subtract_limit(c_print[2], -1 * c_print[8])

                    else:
                        # if the printer status is not finish, failed, or idle, the print is still in progress
                        current_prints[c_print[3]].append((c_print[0], c_print[7]))

            for name in current_prints:
                # iterate through all current prints for each printer
                while len(current_prints[name]) > 1:
                    # if there are multiple current prints for the same printer
                    # get the print id and end time for the oldest print
                    id, end_time = current_prints[name].pop(0)
                    if end_time < timestamp:
                        # if the print's end time is in the past, the print probably succeeded
                        db.archive_print(id, constants.PRINT_SUCCEEDED)
                    else:
                        # if the print's end time is in the future, the print probably was canceled
                        db.archive_print(id, constants.PRINT_CANCELED)

            for printer in printers:
                # iterate through all printers, updating the printer status in the db
                printers[printer].update_db()

            logger.info("main: Finished main loop")
        except Exception as e:
            logger.error(f"main: {traceback.format_exc()}")

            if type(e) == KeyboardInterrupt:
                raise e

except KeyboardInterrupt:
    logger.warning("main: Keyboard interrupt (may up to 60 seconds to stop)")

    for name in printers:
        # stop all printer threads
        logger.info(f"main: Stopping printer {name}")
        printers[name].stop_thread()

    logger.info("main: Stopping account refresh thread")
    account.stop_refresh_thread()

    exit(0)
except Exception:
    logger.error(f"main: {traceback.format_exc()}")
    exit(1)
