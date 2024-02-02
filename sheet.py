import datetime
import json
import os.path
from threading import Thread

import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# get reader id (0 is the control pi, any other number is a reader pi zero)
try:
    reader_file = json.load(open("reader.json"))
except FileNotFoundError:
    print("No reader.json file found.")
    exit(1)
reader_id = reader_file["id"]

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# The ID and sheet names of the access cards sheet.
SPREADSHEET_ID = "1X7VJ9jRQGx0ZryXbvbmff09eOawymLg-DvTY7FYxN2E"
STUDENTS_SHEET = "Students"
STAFF_SHEET = "Staff"
MODULES_SHEET = "Modules"  # contains a mapping from room accesses to combinations of modules ("AND(5, 6, OR(7, 8))" etc)
ACCESSES_SHEET = (
    "Accesses"  # contains a mapping from room accesses to reader ID numbers
)
READERS_SHEET = "Readers"  # contains statuses of the readers
LOG_SHEET = "Log"  # contains a log of all card reads

student_data = None
staff_data = None
module_data = None
access_data = None
reader_data = None

limited_data = False

statuses = ["No Access", "Access"]
reader_headers = [
    "id",
    "status",
    "location",
    "alarm",
    "alarm_delay_min",
    "alarm_status",
    "needs_update",
    "last_checked_in",
]
access_headers = None
this_reader = None

module_count = 0
rooms = list()

creds = None
# The file token.json stores the user's access and refresh tokens, and is
# created automatically when the authorization flow completes for the first
# time.
if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
# If there are no (valid) credentials available, let the user log in.
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open("token.json", "w") as token:
        token.write(creds.to_json())

try:
    service = build("sheets", "v4", credentials=creds)

    # Call the Sheets API
    g_sheets = service.spreadsheets()

except HttpError as e:
    print(e)
    exit(1)


def get_sheet_data(limited=None):
    """
    Get the student and staff data from the Google Sheets document.

    limited: bool: if True, only the UID and accesses will be retrieved, else all data will be retrieved (Name, CruzID, Canvas ID).

    Returns True if the data was retrieved, or False if it was not.
    """
    global student_data, staff_data, module_data, access_data, rooms, module_count, limited_data

    if limited is not None:
        limited_data = limited
    try:
        # get the students sheet
        students = (
            g_sheets.values()
            .get(
                spreadsheetId=SPREADSHEET_ID,
                range=STUDENTS_SHEET + ("!E1:ZZ" if limited_data else ""),
            )
            .execute()
        )
        values = students.get("values", [])

        if not values:
            print("No data found.")
            exit()

        values = [r + [""] * (len(values[0]) - len(r)) for r in values]

        student_data = pd.DataFrame(
            values[1:] if len(values) > 1 else None,
            columns=values[0],
        )

        rooms = student_data.columns.tolist()[5:]

        # get the staff sheet
        staff = (
            g_sheets.values()
            .get(
                spreadsheetId=SPREADSHEET_ID,
                range=STAFF_SHEET + ("!A1:A" if limited_data else ""),
            )
            .execute()
        )
        values = staff.get("values", [])
        values = [r + [""] * (len(values[0]) - len(r)) for r in values]
        staff_data = pd.DataFrame(
            values[1:] if len(values) > 1 else None,
            columns=values[0],
        )

        # get the modules sheet
        modules = (
            g_sheets.values()
            .get(
                spreadsheetId=SPREADSHEET_ID,
                range=MODULES_SHEET,
            )
            .execute()
        )
        values = modules.get("values", [])
        values = [r + [""] * (len(values[0]) - len(r)) for r in values]
        module_data = pd.DataFrame(
            values[1:] if len(values) > 1 else None,
            columns=values[0],
        )

        module_count = len(module_data)

        if reader_id > 0:
            access_headers = ["id", "staff"] + rooms + ["no_access"]

            # get the accesses sheet
            accesses = (
                g_sheets.values()
                .get(
                    spreadsheetId=SPREADSHEET_ID,
                    range=ACCESSES_SHEET
                    + f"!A{reader_id+1}:{str(chr(ord('A') + len(access_headers)))}{reader_id+1}",
                )
                .execute()
            )
            values = accesses.get("values", [])
            access_data = dict()
            for i, r in enumerate(values[0]):
                if access_headers[i] == "id":
                    access_data["id"] = int(0 if not r else r)
                elif not r:
                    access_data[access_headers[i]] = None
                else:
                    r = r.split(", ")
                    if r[1]:
                        r[1] = int(r[1])
                    access_data[access_headers[i]] = tuple(r)

        return True and get_reader_data()
    except HttpError as e:
        print(e)
        return False


def get_reader_data():
    """
    Get the reader data from the Google Sheets document.

    Returns True if the data was retrieved, or False if it was not.
    """
    global reader_data, this_reader
    try:
        # get the readers sheet
        readers = (
            g_sheets.values()
            .get(
                spreadsheetId=SPREADSHEET_ID,
                range=READERS_SHEET,
            )
            .execute()
        )
        values = readers.get("values", [])
        values = [r + [""] * (len(values[0]) - len(r)) for r in values]
        reader_data = pd.DataFrame(
            values[1:] if len(values) > 1 else None,
            columns=values[0],
        )

        this_reader = dict()
        for i, r in enumerate(values[reader_id + 1]):
            this_reader[reader_headers[i]] = r

        this_reader["id"] = 0 if not len(this_reader["id"]) else int(this_reader["id"])
        this_reader["alarm"] = (
            False if not len(this_reader["alarm"]) else this_reader["alarm"] == "ENABLE"
        )
        this_reader["alarm_delay_min"] = (
            0
            if not len(this_reader["alarm_delay_min"])
            else int(this_reader["alarm_delay_min"])
        )
        this_reader["needs_update"] = this_reader["needs_update"] == "PENDING"

        return True
    except HttpError as e:
        print(e)
        return False


def check_in(alarm_status=False):
    """
    Update the reader's last checked in time and needs update status.

    alarm_status: bool: the alarm status (True if the alarm was triggered, False if it was not, and None if it's tagged out).

    Returns True if the data was updated, or False if it was not.
    """
    if this_reader["alarm"] == "DISABLE":
        this_reader["alarm_status"] = "DISABLED"
    else:
        if alarm_status is None:
            this_reader["alarm_status"] = "TAGGED OUT"
        elif alarm_status:
            this_reader["alarm_status"] = "ALARM"
        else:
            this_reader["alarm_status"] = "OK"

    this_reader["last_checked_in"] = str(datetime.datetime.now())
    this_reader["needs_update"] = "DONE"

    try:
        _ = (
            g_sheets.values()
            .update(
                spreadsheetId=SPREADSHEET_ID,
                range=READERS_SHEET + f"!F{reader_id+2}:H{reader_id+2}",
                valueInputOption="USER_ENTERED",
                body={"values": [list(this_reader.values())[-3:]]},
            )
            .execute()
        )
    except HttpError as e:
        print(e)

    get_reader_data()


def student_exists(cruzid=None, canvas_id=None, uid=None):
    """
    Check if a student exists in the database.

    cruzid: str: the student's CruzID if not in limited data mode.
    canvas_id: str: the student's Canvas ID if not in limited data mode.
    uid: str: the student's card UID.

    Returns True if the student exists, or False if they do not.
    """
    return (
        (not limited_data and cruzid and cruzid in student_data["CruzID"].values)
        or (
            not limited_data
            and canvas_id
            and canvas_id in student_data["Canvas ID"].values
        )
        or (uid and uid in student_data["Card UID"].values)
    )


def new_student(first_name, last_name, cruzid, canvas_id=None, uid=None, accesses=None):
    """
    Add a new student to the database (must not be in limited data mode).

    first_name: str: the student's first name.
    last_name: str: the student's last name.
    cruzid: str: the student's CruzID.
    canvas_id: str: the student's Canvas ID (or None).
    uid: str: the student's card UID (or None).
    accesses: list: the student's room accesses (or None).

    Returns True if the student was added, or False if they already exist.
    """
    if (
        limited_data
        or (
            cruzid in student_data["CruzID"].values
            or cruzid in staff_data["CruzID"].values
        )
        or (canvas_id and canvas_id in student_data["Canvas ID"].values)
        or (
            uid
            and (
                uid in student_data["Card UID"].values
                or uid in staff_data["Card UID"].values
            )
        )
    ):
        return False
    student_data.loc[len(student_data)] = [
        first_name,
        last_name,
        cruzid,
        canvas_id if canvas_id else "",
        uid if uid else "",
    ] + ([""] * (len(student_data.columns) - 5))

    if not accesses:
        accesses = [False] * len(rooms)
    set_all_accesses(accesses, cruzid=cruzid)

    return True


def new_staff(first_name, last_name, cruzid, uid=None):
    """
    Add a new staff member to the database (must not be in limited data mode).

    first_name: str: the staff member's first name.
    last_name: str: the staff member's last name.
    cruzid: str: the staff member's CruzID.
    uid: str: the staff member's card UID (or None)

    Returns True if the staff member was added, or False if they already exist.
    """
    if (
        limited_data
        or (
            cruzid in staff_data["CruzID"].values
            or cruzid in student_data["CruzID"].values
        )
        or (
            uid
            and (
                uid in staff_data["Card UID"].values
                or uid in student_data["Card UID"].values
            )
        )
    ):
        return False
    staff_data.loc[len(staff_data)] = [
        first_name,
        last_name,
        cruzid,
        uid if uid else "",
    ]

    return True


def set_uid(cruzid, uid, overwrite=False):
    """
    Set a student or staff's card UID.

    cruzid: str: the CruzID.
    uid: str: the new card UID.
    overwrite: bool: if True, the UID will be overwritten if it already exists.

    Returns the UID if it was set, or the existing UID if it was not set.
    """
    if (
        limited_data
        or (
            cruzid not in student_data["CruzID"].values
            and cruzid not in staff_data["CruzID"].values
        )
        or (
            uid in student_data["Card UID"].values
            or uid in staff_data["Card UID"].values
        )
    ):
        return False

    if cruzid in staff_data["CruzID"].values:
        row = staff_data.index[staff_data["CruzID"] == cruzid].tolist()[0]
        if not staff_data.loc[row, "Card UID"] or overwrite:
            staff_data.loc[row, "Card UID"] = uid
        return staff_data.loc[row, "Card UID"]

    else:
        row = student_data.index[student_data["CruzID"] == cruzid].tolist()[0]
        if not student_data.loc[row, "Card UID"] or overwrite:
            student_data.loc[row, "Card UID"] = uid
        return student_data.loc[row, "Card UID"]


def get_uid(cruzid):
    """
    Get a student's card UID (or False if it doesn't exist).

    cruzid: str: the student's CruzID.

    Returns the student's card UID if it exists, or False if it does not.
    """

    if limited_data or (cruzid not in student_data["CruzID"].values):
        return False

    row = student_data.index[student_data["CruzID"] == cruzid].tolist()[0]
    uid = student_data.loc[row, "Card UID"]
    return uid if uid else False


def set_access(room, access, cruzid=None, uid=None):
    """
    Set a student's access to a room.

    room: str: the room to set access for.
    access: bool: the access to set.
    cruzid: str: the student's CruzID.
    uid: str: the student's card UID.

    Returns the access if it was set, or None if it was not set.
    """

    if (
        (not cruzid and not uid)
        or (
            not limited_data
            and cruzid
            and student_data.index[student_data["CruzID"] == cruzid].empty
        )
        or (uid and student_data.index[student_data["Card UID"] == uid].empty)
        or (
            not limited_data
            and (
                cruzid
                and uid
                and (
                    student_data.index[student_data["CruzID"] == cruzid].tolist()
                    != student_data.index[student_data["Card UID"] == uid].tolist()
                )
            )
        )
        or room not in rooms
    ):
        return None

    if not limited_data and cruzid:
        row = student_data.index[student_data["CruzID"] == cruzid].tolist()[0]
    elif uid:
        row = student_data.index[student_data["Card UID"] == uid].tolist()[0]
    else:
        return None

    if "Override" not in student_data.loc[row, room]:
        student_data.loc[row, room] = statuses[int(access)]
    else:
        access = bool(
            statuses.index(
                student_data.loc[row, room][
                    (
                        len("Override ")
                        if "Override" in student_data.loc[row, room]
                        else 0
                    ) :
                ]
            )
        )
    return access


def get_access(room, cruzid=None, uid=None):
    """
    Get a student's access to a room.

    room: str: the room to get access for.
    cruzid: str: the student's CruzID.
    uid: str: the student's card UID.
    """

    if (
        (not cruzid and not uid)
        or (
            not limited_data
            and cruzid
            and student_data.index[student_data["CruzID"] == cruzid].empty
        )
        or (uid and student_data.index[student_data["Card UID"] == uid].empty)
        or (
            not limited_data
            and (
                cruzid
                and uid
                and (
                    student_data.index[student_data["CruzID"] == cruzid].tolist()
                    != student_data.index[student_data["Card UID"] == uid].tolist()
                )
            )
        )
    ):
        return None

    if not limited_data and cruzid:
        row = student_data.index[student_data["CruzID"] == cruzid].tolist()[0]
    elif uid:
        row = student_data.index[student_data["Card UID"] == uid].tolist()[0]
    else:
        return False

    access = student_data.loc[row, room]

    return (
        bool(
            statuses.index(access[(len("Override ") if "Override" in access else 0) :])
        )
        if access
        else False
    )


def set_all_accesses(accesses, cruzid=None, uid=None):
    """
    Set a student's access to all rooms.

    accesses: list: the accesses to set.
    cruzid: str: the student's CruzID.
    uid: str: the student's card UID.
    """

    if (
        (not cruzid and not uid)
        or (
            not limited_data
            and cruzid
            and student_data.index[student_data["CruzID"] == cruzid].empty
        )
        or (uid and student_data.index[student_data["Card UID"] == uid].empty)
        or (
            not limited_data
            and (
                cruzid
                and uid
                and (
                    student_data.index[student_data["CruzID"] == cruzid].tolist()
                    != student_data.index[student_data["Card UID"] == uid].tolist()
                )
            )
        )
        or len(accesses) != len(rooms)
    ):
        return False

    if not limited_data and cruzid:
        row = student_data.index[student_data["CruzID"] == cruzid].tolist()[0]
    elif uid:
        row = student_data.index[student_data["Card UID"] == uid].tolist()[0]
    else:
        return False

    for i in range(len(rooms)):
        if "Override" not in student_data.loc[row, rooms[i]]:
            student_data.loc[row, rooms[i]] = statuses[int(accesses[i])]
        else:
            accesses[i] = bool(
                statuses.index(
                    student_data.loc[row, rooms[i]][
                        (
                            len("Override ")
                            if "Override" in student_data.loc[row, rooms[i]]
                            else 0
                        ) :
                    ]
                )
            )
    return accesses


def get_all_accesses(cruzid=None, uid=None):
    """
    Get a student's access to all rooms.

    cruzid: str: the student's CruzID.
    uid: str: the student's card UID.
    """

    if (
        (not cruzid and not uid)
        or (
            not limited_data
            and cruzid
            and student_data.index[student_data["CruzID"] == cruzid].empty
        )
        or (uid and student_data.index[student_data["Card UID"] == uid].empty)
        or (
            not limited_data
            and (
                cruzid
                and uid
                and (
                    student_data.index[student_data["CruzID"] == cruzid].tolist()
                    != student_data.index[student_data["Card UID"] == uid].tolist()
                )
            )
        )
    ):
        return False

    if not limited_data and cruzid:
        row = student_data.index[student_data["CruzID"] == cruzid].tolist()[0]
    elif uid:
        row = student_data.index[student_data["Card UID"] == uid].tolist()[0]
    else:
        return False

    accesses = []
    for room in rooms:
        access = student_data.loc[row, room]
        accesses.append(
            bool(
                statuses.index(
                    access[(len("Override ") if "Override" in access else 0) :]
                )
            )
            if access
            else False
        )

    return accesses


def write_student_sheet():
    """
    Write the student data to the Google Sheets document.

    Returns True if the data was written, or False if it was not.
    """

    try:
        student_data.sort_values(by=["Last Name"], inplace=True)
        vals = student_data.values.tolist()
        vals.insert(0, student_data.columns.tolist())

        _ = (
            g_sheets.values()
            .update(
                spreadsheetId=SPREADSHEET_ID,
                range=STUDENTS_SHEET,
                valueInputOption="USER_ENTERED",
                body={"values": vals},
            )
            .execute()
        )
        return True
    except HttpError as e:
        print(e)
        return False


def write_staff_sheet():
    """
    Write the staff data to the Google Sheets document.
    """

    try:
        staff_data.sort_values(by=["Last Name"], inplace=True)
        vals = staff_data.values.tolist()
        vals.insert(0, staff_data.columns.tolist())

        _ = (
            g_sheets.values()
            .update(
                spreadsheetId=SPREADSHEET_ID,
                range=STAFF_SHEET,
                valueInputOption="USER_ENTERED",
                body={"values": vals},
            )
            .execute()
        )
    except HttpError as e:
        print(e)


def evaluate_modules(completed_modules, cruzid=None, uid=None):
    """
    Evaluate a student's completed modules and update their room accesses.

    completed_modules: list: the student's completed modules.
    cruzid: str: the student's CruzID.
    uid: str: the student's card UID.
    """

    for i in range(len(module_data)):
        exp = str(module_data.loc[i, "Modules"])
        for m in range(1, module_count + 1):
            exp = exp.replace(str(m), str(m in completed_modules))
        if (
            set_access(
                module_data.loc[i, "Room"],
                eval(exp) if len(exp) > 0 else False,
                cruzid=cruzid,
                uid=uid,
            )
            is None
        ):
            # print(module_data.loc[i, "Room"], "<" + exp + ">")
            # print(eval(exp))
            # print("fail")
            return False
    return True


def is_staff(cruzid=None, uid=None):
    """
    Check if a student is a staff member.

    cruzid: str: the student's CruzID.
    uid: str: the student's card UID.
    """

    if (
        (not cruzid and not uid)
        or (
            not limited_data
            and cruzid
            and staff_data.index[staff_data["CruzID"] == cruzid].empty
        )
        or (uid and staff_data.index[staff_data["Card UID"] == uid].empty)
        or (
            not limited_data
            and (
                cruzid
                and uid
                and (
                    staff_data.index[staff_data["CruzID"] == cruzid].tolist()
                    != staff_data.index[staff_data["Card UID"] == uid].tolist()
                )
            )
        )
    ):
        return False

    if not limited_data and cruzid:
        return not staff_data.index[staff_data["CruzID"] == cruzid].empty
    elif uid:
        return not staff_data.index[staff_data["Card UID"] == uid].empty
    else:
        return False


def log(uid, access, alarm_status, disarm_time):
    """
    Log a card read.

    uid: str: the card UID.
    access: str: the highest valid room access read at this reader.
    alarm_status: bool: the alarm status (True if the alarm was triggered, False if it was not).
    disarm_time: str: the amount of time the alarm was disarmed for.

    Returns True if the data was logged, or False if it was not.
    """

    try:
        _ = (
            g_sheets.values()
            .append(
                spreadsheetId=SPREADSHEET_ID,
                range=LOG_SHEET,
                valueInputOption="USER_ENTERED",
                body={
                    "values": [
                        [
                            str(datetime.datetime.now()),
                            uid,
                            reader_id,
                            "",  # location
                            "",  # first name
                            "",  # last name
                            "",  # cruzid
                            access,
                            "Triggered" if alarm_status else "Not Triggered",
                            disarm_time,
                        ]
                    ]
                },
            )
            .execute()
        )
        return True
    except HttpError as e:
        print(e)
        return False


def alarm_setting():
    """
    Get the alarm setting from the reader data.

    Returns the alarm enabled/disabled state and alarm delay time in minutes.
    """

    return this_reader["alarm"], this_reader["alarm_delay_min"]


def need_updating():
    """
    Check if this Pi/Zero needs updating.

    Returns True if update needed, or False if not.
    """

    return this_reader["needs_update"]


def scan_uid(uid):
    """
    Return the LED color and alarm delay time for a given card UID.

    uid: str: the card UID.

    Returns the LED hex color and alarm delay time in minutes, or False if no "No Access" value is specified, or None if the uid does not exist.
    """

    if is_staff(uid=uid):
        if access_data["staff"]:
            return access_data["staff"]
        else:
            return False if not access_data["no_access"] else access_data["no_access"]
    elif student_exists(uid=uid):
        for i in range(len(rooms)):
            if get_access(rooms[i], uid=uid) and access_data[rooms[i]]:
                return access_data[rooms[i]]

        return False if not access_data["no_access"] else access_data["no_access"]

    return None


def run_in_thread(f, args, kwargs):
    """
    Run a function in a separate thread.

    f: function: the function to run.
    """

    Thread(target=f, args=args, kwargs=kwargs).start()


def update_all_readers():
    """
    Set all readers to need updating.
    """

    try:
        _ = (
            g_sheets.values()
            .update(
                spreadsheetId=SPREADSHEET_ID,
                range=READERS_SHEET + f"!G3:G{len(reader_data)+1}",
                valueInputOption="USER_ENTERED",
                body={"values": [["PENDING"]] * (len(reader_data) - 1)},
            )
            .execute()
        )
    except HttpError as e:
        print(e)


if __name__ == "__main__":
    get_sheet_data(limited=False)
    print(student_data)
    print()
    print(staff_data)
    print()
    print(access_data)
    print()
    # print(module_data)
    # print()
    print(reader_data)
    print()
    print(this_reader)
    print()

    # print(alarm_enabled, alarm_delay)
    # print(alarm_setting())
    # print(reader_need_updating())

    # update_all_readers()
    check_in()

    # log("Canvas", "", False, 0)

    # print(scan_uid("63B104FF"))
    # print(scan_uid("73B104FF"))
    # print(scan_uid("83B104FF"))
    # print(scan_uid("93B104FF"))

    # student_exists()

    # print time
    # print(str(datetime.datetime.now()))

    # print(get_uid("ewachtel"))
    # print(get_uid("jowemorr"))

    # if not new_student("Cédric", "Chartier", "cchartie"):
    #     print("CruzID, Canvas ID, or Card UID already in use.")

    # print(set_uid("cchartie", "0123456789", overwrite=True))

    # print(set_access("BE-49", False, cruzid="tstudent"))
    # print(get_access("BE-49", uid="0123456789"))
    # print(get_access("BE-49", cruzid="tstudent"))
    # print(set_all_accesses([True] * len(rooms), cruzid="tstudent"))
    # print(get_all_accesses(cruzid="tstudent"))
    # print(evaluate_modules([1, 2, 5, 6, 7, 8, 9, 10], cruzid="tstudent"))

    # write_student_sheet()

    # log("63B104FF", "Staff", True, 10)

    # print()
    # print(student_data)
    # print()
    # print(staff_data)
    # print()
    # print(access_data)
    # # print()
    # # print(module_data)
    # print()
    # print(reader_data)
