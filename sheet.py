import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import pandas as pd

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
    sheet = service.spreadsheets()

    # get the students sheet
    students = (
        sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=STUDENTS_SHEET).execute()
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
        sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=STAFF_SHEET).execute()
    )
    values = staff.get("values", [])
    values = [r + [""] * (len(values[0]) - len(r)) for r in values]
    staff_data = pd.DataFrame(
        values[1:] if len(values) > 1 else None,
        columns=values[0],
    )

except HttpError as e:
    print(e)


def new_student(
    first_name, last_name, cruzid, canvas_id=None, card_uid=None, accesses=None
):
    if (
        cruzid in student_data["CruzID"].values
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
        cruzid not in student_data["CruzID"].values
        or uid in student_data["Card UID"].values
    ):
        return False

    row = student_data.index[student_data["CruzID"] == cruzid].tolist()[0]
    if not student_data.loc[row, "Card UID"] or overwrite:
        student_data.loc[row, "Card UID"] = uid
    return student_data.loc[row, "Card UID"]


def change_uid(cruzid, uid):
    pass


def set_access(room, access, cruzid=None, uid=None):
    if (
        (not cruzid and not uid)
        or (cruzid and student_data.index[student_data["CruzID"] == cruzid].empty)
        or (uid and student_data.index[student_data["Card UID"] == uid].empty)
        or (
            cruzid
            and uid
            and (
                student_data.index[student_data["CruzID"] == cruzid].tolist()
                != student_data.index[student_data["Card UID"] == uid].tolist()
            )
        )
    ):
        return None

    if cruzid:
        row = student_data.index[student_data["CruzID"] == cruzid].tolist()[0]
    elif uid:
        row = student_data.index[student_data["Card UID"] == uid].tolist()[0]

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
        or (cruzid and student_data.index[student_data["CruzID"] == cruzid].empty)
        or (uid and student_data.index[student_data["Card UID"] == uid].empty)
        or (
            cruzid
            and uid
            and (
                student_data.index[student_data["CruzID"] == cruzid].tolist()
                != student_data.index[student_data["Card UID"] == uid].tolist()
            )
        )
    ):
        return None

    if cruzid:
        row = student_data.index[student_data["CruzID"] == cruzid].tolist()[0]
    elif uid:
        row = student_data.index[student_data["Card UID"] == uid].tolist()[0]

    access = student_data.loc[row, room]
    return bool(
        statuses.index(access[(len("Override ") if "Override" in access else 0) :])
    )


def set_all_accesses(accesses, cruzid=None, uid=None):
    if (
        (not cruzid and not uid)
        or (cruzid and student_data.index[student_data["CruzID"] == cruzid].empty)
        or (uid and student_data.index[student_data["Card UID"] == uid].empty)
        or (
            cruzid
            and uid
            and (
                student_data.index[student_data["CruzID"] == cruzid].tolist()
                != student_data.index[student_data["Card UID"] == uid].tolist()
            )
        )
        or len(accesses) != len(rooms)
    ):
        return False

    if cruzid:
        row = student_data.index[student_data["CruzID"] == cruzid].tolist()[0]
    elif uid:
        row = student_data.index[student_data["Card UID"] == uid].tolist()[0]

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
        or (cruzid and student_data.index[student_data["CruzID"] == cruzid].empty)
        or (uid and student_data.index[student_data["Card UID"] == uid].empty)
        or (
            cruzid
            and uid
            and (
                student_data.index[student_data["CruzID"] == cruzid].tolist()
                != student_data.index[student_data["Card UID"] == uid].tolist()
            )
        )
    ):
        return False

    if cruzid:
        row = student_data.index[student_data["CruzID"] == cruzid].tolist()[0]
    elif uid:
        row = student_data.index[student_data["Card UID"] == uid].tolist()[0]

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
            sheet.values()
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


if __name__ == "__main__":
    print(student_data)
    print()
    print(staff_data)
    print()

    # if not new_student("Cédric", "Chartier", "cchartie"):
    #     print("CruzID, Canvas ID, or Card UID already in use.")

    # print(set_uid("cchartie", "0123456789", overwrite=True))

    # print(set_access("BE-49", False, cruzid="tstudent"))
    # print(get_access("BE-49", cruzid="tstudent"))
    # print(set_all_accesses([True] * len(rooms), cruzid="tstudent"))
    # print(get_all_accesses(cruzid="tstudent"))

    write_student_sheet()

    print()
    print(student_data)
    print()
    print(staff_data)
