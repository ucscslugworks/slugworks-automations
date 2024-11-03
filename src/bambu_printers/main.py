import time

from src import constants
from src.bambu_printers import BambuAccount, BambuDB, Printer, StartForm
from src.log import setup_logs

logger = setup_logs("bambu-main")

account = BambuAccount("slugworks@ucsc.edu")
db = BambuDB()
form = StartForm()

devices = account.get_devices()
printers = dict()

for name in devices:
    printers[name] = Printer(account, name, devices[name])

while True:
    try:
        time.sleep(constants.BAMBU_DELAY)
        logger.info("Running main loop")
        # Get the latest row from the start form
        rows = form.get()
        if not rows:
            continue

        # print(1)
        for row in rows:
            if not db.form_exists(row[0]):
                db.add_form(row[0], row[1], row[3], row[2])

        # print(2)
        # Get the latest tasks from the account
        tasks = account.get_tasks()

        # print(3)
        if not tasks:
            continue

        # print(4)
        for task in tasks:
            if not task["isPrintable"] or db.print_exists(task["id"]):
                continue

            # print(5)
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

            # print(6)
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

        # print(7)
        unmatched_forms = db.get_unmatched_forms()
        unmatched_prints = db.get_unmatched_prints()

        timestamp = int(time.time())

        form_printer_rows = dict()
        # print(8)

        for u_form in unmatched_forms:
            if timestamp > u_form[1] + constants.BAMBU_TIMEOUT * 1.1:
                db.expire_form(u_form[0])
            else:
                # Store the form in a dictionary with the printer name as the key and (form row, cruzid) as the value
                form_printer_rows[u_form[2]] = (u_form[0], u_form[3])
            # print(9)

        for u_print in unmatched_prints:
            # print(11)
            if timestamp > u_print[4] + constants.BAMBU_TIMEOUT * 1.1:
                db.expire_print(u_print[0])
                if u_print[6] > timestamp:
                    printers[u_print[1]].cancel()
            elif u_print[1] in form_printer_rows:
                # print(12)
                form_row, cruzid = form_printer_rows[u_print[1]]

                db.match(u_print[0], form_row)
                del form_printer_rows[u_print[1]]

                # print(13)
                if db.get_limit(cruzid) < u_print[6]:
                    printers[u_print[1]].cancel()
                    db.archive_print(u_print[0], constants.PRINT_CANCELED)
                else:
                    db.subtract_limit(cruzid, u_print[6])
                # print(14)

        # print(15)
        # print(16)
    except Exception as e:
        # print(17)
        logger.error(f"main: {e}")
        # print(18)

        if type(e) == KeyboardInterrupt:
            # print(19)
            exit(0)

        # print(20)
        time.sleep(60)
