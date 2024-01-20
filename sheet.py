import os.path

import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# The ID and sheet names of the access cards sheet.
SPREADSHEET_ID = "1X7VJ9jRQGx0ZryXbvbmff09eOawymLg-DvTY7FYxN2E"
STUDENTS_SHEET = "Students"
STAFF_SHEET = "Staff"
MODULES_SHEET = "Modules"  # contains a mapping from room accesses to combinations of modules ("AND(5, 6, OR(7, 8))" etc)
READERS_SHEET = "Readers"  # contains a mapping from room accesses to reader ID numbers

student_data = None
staff_data = None
module_data = None
module_count = 0
limited_data = False

statuses = ["No Access", "Access"]
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
    global student_data, staff_data, module_data, rooms, module_count, limited_data

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

        # get the staff sheet
        staff = (
            g_sheets.values()
            .get(
                spreadsheetId=SPREADSHEET_ID,
                range=MODULES_SHEET,
            )
            .execute()
        )
        values = staff.get("values", [])
        values = [r + [""] * (len(values[0]) - len(r)) for r in values]
        module_data = pd.DataFrame(
            values[1:] if len(values) > 1 else None,
            columns=values[0],
        )

        module_count = len(module_data)

    except HttpError as e:
        print(e)


def student_exists(cruzid=None, canvas_id=None, card_uid=None):
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


def set_access(room, access, cruzid=None, uid=None):
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


# given one student's list of completed modules, update their room accesses
def evaluate_modules(completed_modules, cruzid=None, uid=None):
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


if __name__ == "__main__":
    get_sheet_data(limited=False)
    print(student_data)
    print()
    print(staff_data)
    print()

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

    print()
    print(student_data)
    print()
    print(staff_data)
