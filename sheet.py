import datetime
import json
import os.path

import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# get reader id
reader_file = json.load(open("reader.json"))
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


def get_sheet_data(limited=None):
    """
    Get the student and staff data from the Google Sheets document.

    limited: bool: if True, only the UID and accesses will be retrieved, else all data will be retrieved (Name, CruzID, Canvas ID).
    """
    global student_data, staff_data, module_data, access_data, reader_data, rooms, module_count, limited_data

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
                range=STAFF_SHEET + ("!D1:D" if limited_data else ""),
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

        # get the accesses sheet
        accesses = (
            g_sheets.values()
            .get(
                spreadsheetId=SPREADSHEET_ID,
                range=ACCESSES_SHEET,
            )
            .execute()
        )
        values = accesses.get("values", [])
        values = [r + [""] * (len(values[0]) - len(r)) for r in values]
        access_data = pd.DataFrame(
            values[1:] if len(values) > 1 else None,
            columns=values[0],
        )

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

    except HttpError as e:
        print(e)


def student_exists(cruzid=None, canvas_id=None, card_uid=None):
    """
    Check if a student exists in the database.

    cruzid: str: the student's CruzID if not in limited data mode.
    canvas_id: str: the student's Canvas ID if not in limited data mode.
    card_uid: str: the student's card UID.
    """
    return (
        (not limited_data and cruzid and cruzid in student_data["CruzID"].values)
        or (
            not limited_data
            and canvas_id
            and canvas_id in student_data["Canvas ID"].values
        )
        or (card_uid and card_uid in student_data["Card UID"].values)
    )


def new_student(
    first_name, last_name, cruzid, canvas_id=None, card_uid=None, accesses=None
):
    """
    Add a new student to the database (must not be in limited data mode).

    first_name: str: the student's first name.
    last_name: str: the student's last name.
    cruzid: str: the student's CruzID.
    canvas_id: str: the student's Canvas ID.
    card_uid: str: the student's card UID.
    accesses: list: the student's room accesses.
    """
    if (
        limited_data
        or (cruzid in student_data["CruzID"].values)
        or (canvas_id and canvas_id in student_data["Canvas ID"].values)
        or (card_uid and card_uid in student_data["Card UID"].values)
    ):
        return False
    student_data.loc[len(student_data)] = [
        first_name,
        last_name,
        cruzid,
        canvas_id if canvas_id else "",
        card_uid if card_uid else "",
    ] + ([""] * (len(student_data.columns) - 5))

    if not accesses:
        accesses = [False] * len(rooms)
    set_all_accesses(accesses, cruzid=cruzid)

    return True


def set_uid(cruzid, uid, overwrite=False):
    """
    Set a student's card UID.

    cruzid: str: the student's CruzID.
    uid: str: the student's card UID.
    overwrite: bool: if True, the UID will be overwritten if it already exists.
    """
    if (
        limited_data
        or (cruzid not in student_data["CruzID"].values)
        or uid in student_data["Card UID"].values
    ):
        return False

    row = student_data.index[student_data["CruzID"] == cruzid].tolist()[0]
    if not student_data.loc[row, "Card UID"] or overwrite:
        student_data.loc[row, "Card UID"] = uid
    return student_data.loc[row, "Card UID"]


def get_uid(cruzid):
    """
    Get a student's card UID (or False if it doesn't exist).

    cruzid: str: the student's CruzID.
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
        return False

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
    except HttpError as e:
        print(e)


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


def log(uid, alarm_status, disarm_time):
    """
    Log a card read.

    uid: str: the card UID.
    alarm_status: bool: the alarm status (True if the alarm was triggered, False if it was not).
    disarm_time: str: the amount of time the alarm was disarmed for.
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
                            "Triggered" if alarm_status else "Not Triggered",
                            disarm_time,
                        ]
                    ]
                },
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

    log("63B104FF", True, 10)

    print()
    print(student_data)
    print()
    print(staff_data)
    print()
    print(access_data)
    # print()
    # print(module_data)
    print()
    print(reader_data)
