import os.path
import time
import traceback
from datetime import datetime

from src import constants, log
from src.bambu_printers import (
    bambu_account,
    bambu_db,
    bambu_printer,
    get_account,
    get_db,
    get_printer,
    get_start_form,
    get_status_sheet,
    get_usage_sheet,
    start_form,
    status_sheet,
    usage_sheet,
)

logger = log.setup_logs("bambu_manager", additional_handlers=[("bambu", log.INFO)])

stop_file_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "common",
    "SPECIAL_BAMBU_STOP",
)

pid_file_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "pid_bambu_printers",
)


def load_policy_lists():
    try:
        base_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "common"
        )
        # Exemptions: support both bambu_limit_exempt.json and exemption.json
        exemptions = []
        for fname in ("bambu_limit_exempt.json", "exemption.json"):
            fpath = os.path.join(base_dir, fname)
            if os.path.exists(fpath):
                try:
                    import json

                    with open(fpath, "r") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            exemptions.extend([str(x) for x in data])
                except Exception:
                    logger.warning(f"manager: Failed to read {fname}")

        # Ban list: ban.json if present
        bans = []
        ban_path = os.path.join(base_dir, "ban.json")
        if os.path.exists(ban_path):
            try:
                import json

                with open(ban_path, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        bans.extend([str(x) for x in data])
            except Exception:
                logger.warning("manager: Failed to read ban.json")

        # Deduplicate
        return set(exemptions), set(bans)
    except Exception:
        logger.error(f"manager: {traceback.format_exc()}")
        return set(), set()


def get_new_forms(db: bambu_db.BambuDB, sf: start_form.StartForm):
    # Get the latest rows from the start form
    rows = sf.get()

    # if nothing was returned (possibly because an error occurred) set to empty list
    if not rows:
        rows = []

    logger.debug(f"manager: {len(rows)} forms found")
    for form_row in rows:
        # if the form is not already in the db, add it
        if not db.form_exists(form_row[0]):
            db.add_form(form_row[0], form_row[1], form_row[3], form_row[2])


def get_new_prints(account: bambu_account.BambuAccount, db: bambu_db.BambuDB):
    # Get the latest cloud tasks from the account
    tasks = account.get_tasks()

    # if nothing was returned (possibly because an error occurred) set to empty list
    if not tasks:
        tasks = []

    logger.debug(f"manager: {len(tasks)} tasks found")
    for task in tasks:
        if not task["isPrintable"]:
            # if the task is not a print, skip
            continue
        elif db.is_current_print(task["id"]):
            # if the task is a current print & already in the db, update the cover photo link and skip
            db.update_cover(task["id"], task["cover"])
            continue
        elif db.print_exists(task["id"]):
            # if the task is already in the db (but wasn't a current print), skip
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

        logger.debug(f"manager: adding print {task['id']} to db: {task}")

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


def categorize_forms(db: bambu_db.BambuDB, timestamp: float):
    # dict to store form rows and printer names (as submitted in form) for unmatched forms
    current_rows = dict()

    # dict to store forms from before the timeout for matching with prints before the timeout
    # used if the program hasn't been run for a while and there are unmatched forms + prints that shouldn't be canceled
    old_rows = dict()

    for u_form in db.get_unmatched_forms():
        # iterate through all unmatched forms
        if timestamp > u_form[1] + constants.BAMBU_TIMEOUT:
            # if the form was submitted more than 10 minutes ago (timeout), mark as old
            # store the form in a dictionary with the form row as the key and (name, cruzid, form time) as the value
            old_rows[u_form[0]] = (u_form[2], u_form[3], u_form[1])
        else:
            # Store the form in a dictionary with the printer name as the key and (form row, cruzid) as the value
            # newer forms for the same printer will overwrite older forms - only the most recent form is used
            current_rows[u_form[2]] = (u_form[0], u_form[3])
            # also store the form in old_rows, in case they are within 10 minutes of the print (even if the print is older than 10 min)
            old_rows[u_form[0]] = (u_form[2], u_form[3], u_form[1])

    return current_rows, old_rows


def eval_old_print(
    old_rows: dict[int, tuple],
    u_print: tuple,
    db: bambu_db.BambuDB,
    current_rows: dict[str, tuple],
    printers: dict[str, bambu_printer.Printer],
):
    matched = False  # flag to check if the print was matched
    for form_row in reversed(old_rows):
        # iterate through all old forms
        if old_rows[form_row][0] is None:
            # if the form has already been used, skip
            continue

        name, cruzid, form_time = old_rows[form_row]
        if abs(form_time - u_print[4]) <= constants.BAMBU_TIMEOUT:
            # if the form was submitted within 10 minutes of the print, match them
            logger.debug(
                f"manager: Matching print {u_print[0]} with form {form_row} - old form/print"
            )
            db.match(u_print[0], form_row)
            # Policy checks: ban and concurrency
            exemptions, bans = load_policy_lists()
            if cruzid in bans:
                printers[u_print[1]].cancel()
                db.archive_print(u_print[0], constants.PRINT_CANCELED)
                logger.debug(
                    f"manager: Canceling printer {u_print[1]}, id {u_print[0]} - user {cruzid} is banned"
                )
            elif cruzid not in exemptions:
                active = db.get_active_prints_by_cruzid(cruzid)
                if any(p[0] != u_print[0] for p in active):
                    printers[u_print[1]].cancel()
                    db.archive_print(u_print[0], constants.PRINT_CANCELED)
                    logger.debug(
                        f"manager: Canceling printer {u_print[1]}, id {u_print[0]} - user {cruzid} already has an active print"
                    )
                else:
                    db.subtract_limit(cruzid, u_print[6])
                    logger.debug(
                        f"manager: User {cruzid} has sufficient weight for print {u_print[0]}"
                    )
            else:
                # exempt user: ignore concurrency and limits
                db.subtract_limit(cruzid, u_print[6])
            matched = True
            old_rows[form_row] = (None,)  # mark the form as used
            if name in current_rows and current_rows[name][0] == form_row:
                # if there has been no newer form for the same printer, mark the form as matched in current_rows
                del current_rows[name]

            break

    if not matched:
        # if the print was not matched, expire it
        logger.debug(f"manager: Expiring print {u_print[0]} - old print, no form found")
        db.expire_print(u_print[0])
        logger.debug(
            f"manager: print started at {u_print[4]}, printer started at {printers[u_print[1]].start_time}"
        )
        if abs(u_print[4] - printers[u_print[1]].start_time) <= 90:
            # if the start time in the print task is within 90 seconds of the printer's current print's start time, they must be the same print
            # cancel the print (no form was submitted/matched)
            printers[u_print[1]].cancel()
            logger.debug(
                f"manager: Canceling printer {u_print[1]}, id {u_print[0]} - old print, no form found, still running"
            )
        else:
            logger.debug(
                f"manager: Not canceling printer {u_print[1]} - job started at {u_print[4]}, printer reports start time {printers[u_print[1]].start_time}"
            )

    return current_rows, old_rows


def match_print(
    current_rows: dict[str, tuple],
    u_print: tuple,
    db: bambu_db.BambuDB,
    printers: dict[str, bambu_printer.Printer],
):
    # if the print was submitted within the last 10 minutes and there is a form for the same printer (and the print is still running)
    # get the form details
    form_row, cruzid = current_rows[u_print[1]]

    # match the print with the form and remove the form from current_rows
    db.match(u_print[0], form_row)
    del current_rows[u_print[1]]

    logger.debug(
        f"manager: Matching print {u_print[0]} with form {form_row} - new form/print, still running"
    )

    # Load policy lists
    exemptions, bans = load_policy_lists()

    # Ban enforcement: cancel immediately
    if cruzid in bans:
        printers[u_print[1]].cancel()
        db.archive_print(u_print[0], constants.PRINT_CANCELED)
        logger.debug(
            f"manager: Canceling printer {u_print[1]}, id {u_print[0]} - user {cruzid} is banned"
        )
        return current_rows

    # Concurrency enforcement: non-exempt users limited to one active print
    if cruzid not in exemptions:
        active = db.get_active_prints_by_cruzid(cruzid)
        # If there is any other active print, cancel this one
        if any(p[0] != u_print[0] for p in active):
            printers[u_print[1]].cancel()
            db.archive_print(u_print[0], constants.PRINT_CANCELED)
            logger.debug(
                f"manager: Canceling printer {u_print[1]}, id {u_print[0]} - user {cruzid} already has an active print"
            )
            return current_rows

    # check if the user has enough weight left in their limit
    if db.get_limit(cruzid) < u_print[6]:
        # if the user does not have enough weight left, cancel the print
        printers[u_print[1]].cancel()
        # archive the print as canceled
        db.archive_print(u_print[0], constants.PRINT_CANCELED)

        logger.debug(
            f"manager: Canceling printer {u_print[1]}, id {u_print[0]} - new form/print, still running, user {cruzid} has insufficient weight"
        )
    else:
        # if the user has enough weight left, subtract the print weight from their limit
        db.subtract_limit(cruzid, u_print[6])

        logger.debug(
            f"manager: User {cruzid} has sufficient weight for print {u_print[0]}"
        )

    return current_rows


def check_unmatched_prints(
    db: bambu_db.BambuDB,
    timestamp: float,
    current_rows: dict[str, tuple],
    old_rows: dict[int, tuple],
    printers: dict[str, bambu_printer.Printer],
):
    for u_print in db.get_unmatched_prints():
        # iterate through all unmatched prints
        if timestamp > u_print[4] + constants.BAMBU_TIMEOUT:
            # if the print was submitted more than 10 minutes ago (timeout), compare with old forms
            logger.debug(
                f"manager: Print {u_print[0]} is older than timeout, checking old forms"
            )
            current_rows, old_rows = eval_old_print(
                old_rows, u_print, db, current_rows, printers
            )

        elif (
            u_print[1] in current_rows
            and abs(u_print[4] - printers[u_print[1]].start_time) <= 90
        ):
            current_rows = match_print(current_rows, u_print, db, printers)


def expire_old_forms(
    old_rows: dict[int, tuple], db: bambu_db.BambuDB, timestamp: float
):
    # expire any forms that were not matched and are older than 10 minutes
    for form_row in old_rows:
        # check if the form was used
        if (
            old_rows[form_row][0] is not None
            and old_rows[form_row][2] + constants.BAMBU_TIMEOUT < timestamp
        ):
            db.expire_form(form_row)
            logger.debug(
                f"manager: Expiring form {form_row} - old form, no print found"
            )


def check_current_prints(db: bambu_db.BambuDB, timestamp: float):
    # dict to store current prints for each printer (in case there are multiple)
    current_prints = dict()

    # iterate through all current prints
    for c_print in db.get_current_prints():

        if c_print[3] not in current_prints:
            # if the printer is not in the dict, add this print as the current print
            current_prints[c_print[3]] = c_print
        else:
            # if this printer is in the dict, compare the start times
            if c_print[6] >= current_prints[c_print[3]][6]:
                # if this print's start time is more recent, archive the old print and add this print as the current print
                if current_prints[c_print[3]][7] > timestamp:
                    # if the print's end time is in the future, the print probably was canceled

                    logger.debug(
                        f"manager: Print {current_prints[c_print[3]][0]} was probably canceled"
                    )
                    db.archive_print(
                        current_prints[c_print[3]][0],
                        constants.PRINT_CANCELED,
                    )
                    # add the print weight back to the user's limit
                    db.subtract_limit(
                        current_prints[c_print[3]][2],
                        -1 * current_prints[c_print[3]][8],
                    )
                else:
                    # if the print's end time is in the past, the print probably succeeded

                    logger.debug(
                        f"manager: Print {current_prints[c_print[3]][0]} probably succeeded"
                    )
                    db.archive_print(
                        current_prints[c_print[3]][0],
                        constants.PRINT_SUCCEEDED,
                    )

                logger.debug(
                    f"manager: Replacing print {current_prints[c_print[3]][0]} with print {c_print[0]} as the current print for {c_print[3]}"
                )
                current_prints[c_print[3]] = c_print

    # return the current prints, used to update the printers
    return current_prints


def update_printers(
    printers: dict[str, bambu_printer.Printer],
    current_prints: dict[int, tuple],
    timestamp: float,
    db: bambu_db.BambuDB,
):
    for name in printers:
        printer = printers[name]
        running = False

        if name in current_prints:
            print_details = current_prints[name]

            if print_details[6] <= timestamp - 90:
                # if print start time is more than 90 seconds ago (ignore very recent prints in case the printer object status hasn't updated yet)
                if printer.get_status() == constants.GCODE_FINISH:
                    # if the printer status is finish, the print succeeded
                    logger.debug(f"manager: Print {print_details[0]} succeeded")
                    db.archive_print(print_details[0], constants.PRINT_SUCCEEDED)
                elif printer.get_status() == constants.GCODE_FAILED:
                    # if the printer status is failed, the print failed
                    logger.debug(f"manager: Print {print_details[0]} failed")
                    db.archive_print(print_details[0], constants.PRINT_FAILED)
                    # add the print weight back to the user's limit
                    db.subtract_limit(print_details[2], -1 * print_details[8])
                elif printer.get_status() == constants.GCODE_IDLE:
                    # if the printer status is idle, the print was canceled
                    logger.debug(f"manager: Print {print_details[0]} canceled")
                    db.archive_print(print_details[0], constants.PRINT_CANCELED)
                    # add the print weight back to the user's limit
                    db.subtract_limit(print_details[2], -1 * print_details[8])
                else:
                    # if the printer status is not finish, failed, or idle, the print is still in progress
                    running = True
                    logger.debug(
                        f"manager: Print {print_details[0]} still running on printer {name}, updating end time and status"
                    )
                    db.update_print_end_time(print_details[0], printer.get_end_time())
                    db.update_printer(
                        name,
                        status=constants.PRINTER_MATCHED,
                        print_id=print_details[0],
                        cruzid=print_details[2],
                    )

        if not running:
            logger.debug(f"manager: Marking printer {name} as idle")
            db.update_printer(
                name,
                status=constants.PRINTER_IDLE,
                print_id=-1,
                cruzid="",
            )

        printer.update_db()
        printer.restart_bpm_object()


def update_status_sheet(
    db: bambu_db.BambuDB,
    printers: dict[str, bambu_printer.Printer],
    ss: status_sheet.StatusSheet,
):
    # check if any printers have not been updated in a while (using offline timeout) and mark them as offline
    db.check_offline_printers()

    # update the status sheet with the latest data
    data = {}
    for name in printers:
        # for each printer, get the latest data from the printer table
        data[name] = db.get_printer_data(name)

        # if the printer currently has an ongoing print, get its print id and find the weight of the print (else 0)
        data[name]["weight"] = (
            0
            if data[name]["print_id"] < 0
            else db.get_print_weight(data[name]["print_id"])
        )

    # update status sheet
    ss.update(data)


def build_usage_rows(db: bambu_db.BambuDB):
    """Build rows for the usage sheet: [cruzid, used_g, remaining_g, status, last_updated]."""
    exemptions, bans = load_policy_lists()
    limits = db.get_limits_snapshot()
    usage_totals = db.get_usage_totals()

    rows = [["cruzid", "used_g", "remaining_g", "status", "last_updated"]]
    now = datetime.utcnow().isoformat()
    seen = set()

    def remaining_display(cruzid, remaining):
        if cruzid in bans:
            return 0 if remaining is None else remaining
        if cruzid in exemptions:
            return "Exempt"
        return "" if remaining is None else remaining

    def status_label(cruzid):
        if cruzid in bans:
            return "Banned"
        if cruzid in exemptions:
            return "Exempt"
        return "Active"

    def used_display(cruzid, remaining):
        if cruzid in exemptions:
            return usage_totals.get(cruzid, 0)
        if remaining is None:
            return usage_totals.get(cruzid, 0)
        return round(constants.BAMBU_DEFAULT_LIMIT - remaining, 2)

    for cruzid, remaining in limits:
        seen.add(cruzid)
        rows.append(
            [
                cruzid,
                used_display(cruzid, remaining),
                remaining_display(cruzid, remaining),
                status_label(cruzid),
                now,
            ]
        )

    for cruzid, total in usage_totals.items():
        if cruzid in seen:
            continue
        remaining = db.get_limit(cruzid)
        rows.append(
            [
                cruzid,
                used_display(cruzid, remaining),
                remaining_display(cruzid, remaining),
                status_label(cruzid),
                now,
            ]
        )

    rows[1:] = sorted(rows[1:], key=lambda r: r[0])
    return rows


def manager():
    logger.info("manager: Starting setup")
    account = get_account()
    db = get_db()
    sf = get_start_form()
    ss = get_status_sheet()
    us = get_usage_sheet()

    devices = account.get_devices()
    printers = dict()

    for name in devices:
        printers[name] = get_printer(name, devices[name])

    logger.info("manager: Finished setup")

    try:
        # main loop
        while True:
            try:
                logger.info("manager: Running main loop")

                # loop timestamp - ensure consistent time comparisons for all operations in this loop
                timestamp = int(time.time())

                # get the latest forms from the start form
                logger.info("manager: Checking for new forms")
                get_new_forms(db, sf)

                # get the latest prints from the account
                logger.info("manager: Checking for new prints")
                get_new_prints(account, db)

                # check unmatched form responses - either mark them as old or current
                logger.info("manager: Checking unmatched form responses")
                current_form_rows, old_form_rows = categorize_forms(db, timestamp)

                # check unmatched prints - either match them with forms or expire them
                logger.info("manager: Checking unmatched prints for expiry/matching")
                check_unmatched_prints(
                    db, timestamp, current_form_rows, old_form_rows, printers
                )

                # expire any forms that were not matched and are older than 10 minutes
                logger.info("manager: Expiring old forms")
                expire_old_forms(old_form_rows, db, timestamp)

                # create a list of "current prints" - prints that should be running based on db
                logger.info("manager: Checking current prints for status changes")
                current_prints = check_current_prints(db, timestamp)

                # check the printers - update the db based on the status of each print that's actually running
                logger.info("manager: Updating printers and print statuses")
                update_printers(printers, current_prints, timestamp, db)

                # update the status sheet with the latest data
                logger.info("manager: Updating status sheet")
                update_status_sheet(db, printers, ss)

                # update the usage sheet with per-user totals
                logger.info("manager: Updating usage sheet")
                usage_rows = build_usage_rows(db)
                us.update(usage_rows)

                logger.info("manager: Finished main loop")

                # check if the stop file exists - if it does, raise a KeyboardInterrupt (to stop the program)
                if os.path.exists(stop_file_path):
                    logger.warning(
                        "manager: SPECIAL_BAMBU_STOP file found, triggering KeyboardInterrupt"
                    )

                    os.remove(stop_file_path)
                    raise KeyboardInterrupt

                # delay between loops
                time.sleep(constants.BAMBU_DELAY)

            except Exception as e:
                # log the exception
                logger.error(f"manager: {traceback.format_exc()}")

                # if the exception is a KeyboardInterrupt, raise it (to stop the program)
                if type(e) == KeyboardInterrupt:
                    raise e

                # in case an exception occurs, wait for a while before continuing
                time.sleep(constants.BAMBU_DELAY)

    # if a KeyboardInterrupt is raised, stop the program
    except KeyboardInterrupt:
        logger.warning("manager: Keyboard interrupt (may up to 2 minutes to stop)")

        # stop all printer threads
        for name in printers:
            # stop all printer threads
            logger.info(f"manager: Stopping printer {name}")
            printers[name].stop_thread()

        # stop the account refresh thread
        logger.info("manager: Stopping account refresh thread")
        account.stop_refresh_thread()

    # if any other exception is raised, log it and stop the program
    except Exception:
        logger.error(f"manager: {traceback.format_exc()}")

    # remove the pid file if it exists
    if os.path.exists(pid_file_path):
        logger.info("manager: pid_bambu_printers file found, deleting")
        os.remove(pid_file_path)

    logger.warning("manager: stopped")


if __name__ == "__main__":
    manager()
