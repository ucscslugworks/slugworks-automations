import os
import sqlite3
import time

from .. import log

READER_ONLINE = 1
READER_OFFLINE = 0

ALARM_ENABLE = 1
ALARM_DISABLE = 0

ALARM_STATUS_OK = 0
ALARM_STATUS_ALARM = 1
ALARM_STATUS_TAGGEDOUT = 2
ALARM_STATUS_DISABLED = 3

CANVAS_OK = 0
CANVAS_UPDATING = 1
CANVAS_PENDING = 2

ACCESS_NO = 0
ACCESS_YES = 1
ACCESS_NO_OVERRIDE = 2
ACCESS_YES_OVERRIDE = 3

# Change directory to repository root
path = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
os.chdir(path)

logger = log.setup_logs("server", log.INFO)

db = sqlite3.connect("src/server/access.db", autocommit=True)
cursor = db.cursor()
sql = cursor.execute

CREATE_TABLES = [
    ("students", "(cruzid TEXT, firstname TEXT, lastname TEXT, uid TEXT)"),
    ("staff", "(cruzid TEXT, firstname TEXT, lastname TEXT, uid TEXT)"),
    ("rooms", "(name TEXT, modules_expr TEXT)"),
    ("accesses", "(reader_id INTEGER, staff TEXT, no_access TEXT)"),
    (
        "readers",
        "(reader_id INTEGER, online INTEGER, location TEXT, alarm_enable INTEGER, alarm_delay_min INTEGER, alarm_status INTEGER, last_seen REAL)",
    ),
    ("canvas_status", "(status INTEGER, timestamp REAL)"),
    ("tagout", "(uid TEXT)"),
    ("offline_timeout", "(timeout_min INTEGER)"),
    ("canvas_course_id", "(id INTEGER)"),
]

for name, params in CREATE_TABLES:
    sql(f"CREATE TABLE IF NOT EXISTS {name} {params}")

if not sql("SELECT * FROM canvas_status").fetchone():
    sql(f"INSERT INTO canvas_status (status, timestamp) VALUES ({CANVAS_OK}, -1)")

if not sql("SELECT * FROM tagout").fetchone():
    sql("INSERT INTO tagout (uid) VALUES ('')")

if not sql("SELECT * FROM offline_timeout").fetchone():
    sql("INSERT INTO offline_timeout (timeout_min) VALUES (15)")

if not sql("SELECT * FROM canvas_course_id").fetchone():
    sql("INSERT INTO canvas_course_id (id) VALUES (0)")

# TODO: should access logs be stored in a database or in a .log file?


def add_student(cruzid: str, firstname: str, lastname: str, uid: str | None = None):
    """
    Add a new student to the database
    """
    if uid is None:
        uid = ""

    if not cruzid.isalnum():
        logger.warning(f"add_student: Student {cruzid} is not alphanumeric")
        return False
    # elif any([not c.isalpha() and c != " " for c in firstname]):
    #     logger.warning(f"add_student: First name {firstname} is not alphabetic")
    #     return False
    # elif any([not c.isalpha() and c != " " for c in lastname]):
    #     logger.warning(f"add_student: Last name {lastname} is not alphabetic")
    #     return False
    elif not uid.isalnum() and uid != "":
        logger.warning(f"add_student: UID {uid} is not alphanumeric")
        return False

    uid = uid.lower()

    if sql("SELECT * FROM students WHERE cruzid = ?", (cruzid,)).fetchone():
        logger.warning(f"add_student: Student {cruzid} already exists in the database")
        return False
    elif sql("SELECT * FROM staff WHERE cruzid = ?", (cruzid,)).fetchone():
        logger.warning(
            f"add_student: Student {cruzid} already exists as staff in the database"
        )
        return False
    elif uid and (
        sql("SELECT * FROM students WHERE uid = ?", (uid,)).fetchone()
        or sql("SELECT * FROM staff WHERE uid = ?", (uid,)).fetchone()
    ):
        logger.warning(f"add_student: UID {uid} already exists in the database")
        return False

    sql(
        "INSERT INTO students (cruzid, firstname, lastname, uid) VALUES (?, ?, ?, ?)",
        (cruzid, firstname, lastname, uid),
    )
    logger.info(f"add_student: Added student {cruzid} to the database")
    return True


def remove_student(cruzid: str):
    """
    Remove a student from the database
    """
    if not cruzid.isalnum():
        logger.warning(f"remove_student: Student {cruzid} is not alphanumeric")
        return False

    if not sql("SELECT * FROM students WHERE cruzid = ?", (cruzid,)).fetchone():
        logger.warning(
            f"remove_student: Student {cruzid} does not exist in the database"
        )
        return False

    sql("DELETE FROM students WHERE cruzid = ?", (cruzid,))
    logger.info(f"remove_student: Removed student {cruzid} from the database")
    # TODO: archive list for removed students
    return True


def is_student(cruzid: str | None = None, uid: str | None = None):
    """
    Check if a given cruzid or uid belongs to a student in the database
    """

    if cruzid:
        cruzid = cruzid.lower()

    if uid:
        uid = uid.lower()

    return bool(
        (
            cruzid
            and sql("SELECT * FROM students WHERE cruzid = ?", (cruzid,)).fetchone()
        )
        or (uid and sql("SELECT * FROM students WHERE uid = ?", (uid,)).fetchone())
    )


def clamp_students(student_list: list):
    """
    Clamp the student db to the given list
    """

    students = sql("SELECT cruzid FROM students").fetchall()
    for s in students:
        if s[0] not in student_list:
            if not remove_student(s[0]):
                return False

    return True


def add_staff(cruzid: str, firstname: str, lastname: str, uid: str | None = None):
    """
    Add a new staff member to the database
    """
    if uid is None:
        uid = ""

    if not cruzid.isalnum():
        logger.warning(f"add_staff: Student {cruzid} is not alphanumeric")
        return False
    # elif any([not c.isalpha() and c != " " for c in firstname]):
    #     logger.warning(f"add_staff: First name {firstname} is not alphabetic")
    #     return False
    # elif any([not c.isalpha() and c != " " for c in lastname]):
    #     logger.warning(f"add_staff: Last name {lastname} is not alphabetic")
    #     return False
    elif not uid.isalnum() and uid != "":
        logger.warning(f"add_staff: UID {uid} is not alphanumeric")
        return False

    uid = uid.lower()

    if sql("SELECT * FROM staff WHERE cruzid = ?", (cruzid,)).fetchone():
        logger.warning(f"add_staff: Staff {cruzid} already exists in the database")
        return False
    elif sql("SELECT * FROM students WHERE cruzid = ?", (cruzid,)).fetchone():
        logger.warning(
            f"add_staff: Staff {cruzid} already exists as student in the database"
        )
        return False
    elif uid and (
        sql("SELECT * FROM students WHERE uid = ?", (uid,)).fetchone()
        or sql("SELECT * FROM staff WHERE uid = ?", (uid,)).fetchone()
    ):
        logger.warning(f"add_student: UID {uid} already exists in the database")
        return False
    sql(
        "INSERT INTO staff (cruzid, firstname, lastname, uid) VALUES (?, ?, ?, ?)",
        (cruzid, firstname, lastname, uid),
    )
    logger.info(f"add_staff: Added staff {cruzid} to the database")
    return True


def remove_staff(cruzid: str):
    """
    Remove a staff member from the database
    """
    if not cruzid.isalnum():
        logger.warning(f"remove_staff: Staff {cruzid} is not alphanumeric")
        return False

    if not sql("SELECT * FROM staff WHERE cruzid = ?", (cruzid,)).fetchone():
        logger.warning(f"remove_staff: Staff {cruzid} does not exist in the database")
        return False

    sql("DELETE FROM staff WHERE cruzid = ?", (cruzid,))
    logger.info(f"remove_staff: Removed staff {cruzid} from the database")
    return True


def is_staff(cruzid: str | None = None, uid: str | None = None):
    """
    Check if a given cruzid or uid belongs to a staff member in the database
    """

    if cruzid:
        cruzid = cruzid.lower()

    if uid:
        uid = uid.lower()

    return bool(
        (cruzid and sql("SELECT * FROM staff WHERE cruzid = ?", (cruzid,)).fetchone())
        or (uid and sql("SELECT * FROM staff WHERE uid = ?", (uid,)).fetchone())
    )


def clamp_staff(staff_list: list):
    """
    Clamp the staff db to the given list
    """

    staff = sql("SELECT cruzid FROM staff").fetchall()
    for s in staff:
        if s[0] not in staff_list:
            if not remove_staff(s[0]):
                return False

    return True


def user_exists(cruzid: str | None = None, uid: str | None = None):
    """
    Call both is_student and is_staff - does a user with the given details exist
    """
    return is_student(cruzid=cruzid, uid=uid) or is_staff(cruzid=cruzid, uid=uid)


def get_user_data(cruzid: str | None = None, uid: str | None = None):
    """
    Get a user's data for the identify page.
    """

    if is_student(cruzid=cruzid, uid=uid):
        rooms = sql("SELECT name FROM rooms").fetchall()

        data = None
        if cruzid:
            data = sql(
                "SELECT cruzid, firstname, lastname, uid FROM students WHERE cruzid = ?",
                (cruzid,),
            ).fetchone()
        elif uid:
            data = sql(
                "SELECT cruzid, firstname, lastname, uid FROM students WHERE uid = ?",
                (uid,),
            ).fetchone()

        if not data:
            logger.error(
                f"get_user_data: Student {cruzid} {uid} not found, yet exists based on is_student"
            )
            return False

        data_dict = {
            "type": "student",
            "cruzid": data[0],
            "firstname": data[1],
            "lastname": data[2],
            "uid": data[3],
        }

        for room in rooms:
            data_dict[room[0]] = get_access(room[0], cruzid=data[0])

        return data_dict
    elif is_staff(cruzid=cruzid, uid=uid):
        data = None
        if cruzid:
            data = sql(
                "SELECT cruzid, firstname, lastname, uid FROM staff WHERE cruzid = ?",
                (cruzid,),
            ).fetchone()
        elif uid:
            data = sql(
                "SELECT cruzid, firstname, lastname, uid FROM staff WHERE uid = ?",
                (uid,),
            ).fetchone()

        if not data:
            logger.error(
                f"get_user_data: Staff member {cruzid} {uid} not found, yet exists based on is_staff"
            )
            return False

        return {
            "type": "staff",
            "cruzid": data[0],
            "firstname": data[1],
            "lastname": data[2],
            "uid": data[3],
        }

    return False


def set_uid(cruzid: str, uid: str, overwrite: bool = False):
    """
    Set a student or staff member's card UID
    """

    if (
        not cruzid
        or not uid
        or not user_exists(cruzid=cruzid)
        or (user_exists(uid=uid) and not overwrite)
    ):
        return False

    if overwrite:
        sql("UPDATE students SET uid = ? WHERE uid = ?", ("", uid))
        sql("UPDATE staff SET uid = ? WHERE uid = ?", ("", uid))

    sql("UPDATE students SET uid = ? WHERE cruzid = ?", (uid, cruzid))
    sql("UPDATE staff SET uid = ? WHERE cruzid = ?", (uid, cruzid))


def get_uid(cruzid: str):
    if not user_exists(cruzid=cruzid):
        return False

    data = (
        sql("SELECT uid FROM students WHERE cruzid = ?", (cruzid,)).fetchone()
        + sql("SELECT uid FROM staff WHERE cruzid = ?", (cruzid,)).fetchone()
    )
    return data[0][0]


def get_cruzid(uid: str):
    if not user_exists(uid=uid):
        return False

    data = (
        sql("SELECT cruzid FROM students WHERE uid = ?", (uid,)).fetchone()
        + sql("SELECT cruzid FROM staff WHERE uid = ?", (uid,)).fetchone()
    )
    return data[0][0]


def set_access(room: str, access: int, cruzid: str):
    if not is_room(room) or not is_student(cruzid=cruzid):
        # TODO: separate, log individual warnings
        return False

    sql(f"UPDATE students SET {room} = ? WHERE cruzid = ?", (access, cruzid))
    return True


def get_access(room: str, cruzid: str | None = None, uid: str | None = None):
    if not is_room(room):
        logger.error(f"get_access: Room {room} does not exist in db")
        return False
    elif not is_student(cruzid=cruzid) and not is_student(uid=uid):
        logger.error(
            f"get_access: Student with cruzid {cruzid} and/or uid {uid} does not exist in db"
        )
        return False

    access = None
    if cruzid:
        access = sql(
            f"SELECT {room} FROM students WHERE cruzid = ?", (cruzid,)
        ).fetchone()[0]
    elif uid:
        access = sql(f"SELECT {room} FROM students WHERE uid = ?", (uid,)).fetchone()[0]

    if access is None:
        return ACCESS_NO
    else:
        return access


def add_room(name: str, modules_expr: str):
    """
    Add a new room
    """
    name = name.strip().replace(" ", "_")

    if any([not c.isalnum() and c != "_" for c in name]):
        logger.warning(f"add_room: Room {name} is not alphanumeric")
        return False

    if not name[0].isalpha():
        logger.warning(f"add_room: Room {name} does not start with a letter")
        return False

    if sql("SELECT * FROM rooms WHERE name = ?", (name,)).fetchone():
        logger.warning(f"add_room: Room {name} already exists in the database")
        return False

    sql(
        "INSERT INTO rooms (name, modules_expr) VALUES (?, ?)",
        (name, modules_expr),
    )
    sql(f"ALTER TABLE accesses ADD COLUMN {name} TEXT")
    sql(f"ALTER TABLE students ADD COLUMN {name} INTEGER")
    logger.info(f"add_room: Added room {name} to the database")
    return True


def remove_room(name: str):
    """
    Remove a room
    """
    if any([not c.isalnum() and c != "_" for c in name]):
        logger.warning(f"remove_room: Room {name} is not alphanumeric")
        return False

    if not sql("SELECT * FROM rooms WHERE name = ?", (name,)).fetchone():
        logger.warning(f"remove_room: Room {name} does not exist in the database")
        return False

    sql("DELETE FROM rooms WHERE name = ?", (name,))
    sql(f"ALTER TABLE accesses DROP COLUMN {name}")
    sql(f"ALTER TABLE students DROP COLUMN {name}")
    logger.info(f"remove_room: Removed room {name} from the database")
    return True


def change_room_modules(name: str, modules_expr: str):
    """
    Change the modules expression for a room
    """
    if not is_room(name):
        logger.warning(
            f"change_room_modules: Room {name} does not exist in the database"
        )
        return False

    sql("UPDATE rooms SET modules_expr = ? WHERE name = ?", (modules_expr, name))
    logger.info(f"change_room_modules: Updated room {name} in the database")
    return True


def is_room(name: str):
    return bool(name and sql("SELECT * FROM rooms WHERE name = ?", (name,)))


def add_reader(location: str, alarm_enable: bool, alarm_delay_min: int):
    """
    Add a reader and return its ID
    """
    reader_id = 0
    while sql("SELECT * FROM readers WHERE reader_id = ?", (str(reader_id))).fetchone():
        reader_id += 1

    sql(
        "INSERT INTO readers (reader_id, online, location, alarm_enable, alarm_delay_min, alarm_status, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            reader_id,
            READER_OFFLINE,
            location,
            ALARM_ENABLE if alarm_enable else ALARM_DISABLE,
            alarm_delay_min,
            ALARM_STATUS_OK if alarm_enable else ALARM_STATUS_DISABLED,
            -1,
        ),
    )

    sql("INSERT INTO accesses (reader_id) VALUES (?)", (str(reader_id)))

    return reader_id


def remove_reader(reader_id: int):
    """
    Remove a reader
    """
    if not sql(
        "SELECT * FROM readers WHERE reader_id = ?", (str(reader_id))
    ).fetchone():
        logger.warning(f"remove_reader: No reader with ID {reader_id}")
        return False

    sql("DELETE FROM readers WHERE reader_id = ?", (str(reader_id)))
    sql("DELETE FROM accesses WHERE reader_id = ?", (str(reader_id)))

    return True


def get_reader_settings(reader_id: int):
    """
    Get a particular reader's location, alarm enable, and alarm delay time settings
    """
    if not sql(
        "SELECT * FROM readers WHERE reader_id = ?", (str(reader_id))
    ).fetchone():
        logger.warning(f"get_reader_settings: No reader with ID {reader_id}")
        return False

    return sql(
        "SELECT location, alarm_enable, alarm_delay_min FROM readers WHERE reader_id = ?",
        (str(reader_id)),
    ).fetchone()


def set_reader_settings(
    reader_id: int,
    location: str | None,
    alarm_enable: bool | None,
    alarm_delay_min: int | None,
):
    """
    Set a particular reader's location, alarm enable, and alarm delay time settings
    """
    if not sql(
        "SELECT * FROM readers WHERE reader_id = ?", (str(reader_id))
    ).fetchone():
        logger.warning(f"set_reader_settings: No reader with ID {reader_id}")
        return False

    if location is not None:
        sql(
            "UPDATE readers SET location = ? WHERE reader_id = ?",
            (location, reader_id),
        )
    if alarm_enable is not None:
        sql(
            "UPDATE readers SET alarm_enable = ? WHERE reader_id = ?",
            (ALARM_ENABLE if alarm_enable else ALARM_DISABLE, reader_id),
        )
    if alarm_delay_min is not None:
        sql(
            "UPDATE readers SET alarm_delay_min = ? WHERE reader_id = ?",
            (alarm_delay_min, reader_id),
        )

    return True


def check_in(reader_id: int):
    """
    Check in a reader: update its last seen time to now
    """
    if not sql(
        "SELECT * FROM readers WHERE reader_id = ?", (str(reader_id))
    ).fetchone():
        logger.warning(f"check_in: No reader with ID {reader_id}")
        return False

    sql(
        "UPDATE readers SET last_seen = ? WHERE reader_id = ?", (time.time(), reader_id)
    )
    return True


def set_reader_online_statuses():
    """
    Parse all readers, use their last seen timestamps to determine online/offline status
    """
    readers = sql("SELECT reader_id, last_seen FROM readers").fetchall()

    if not readers:
        return False

    ref_time = time.time()
    for reader_id, timestamp in readers:
        sql(
            "UPDATE readers SET online = ? WHERE reader_id = ?",
            (
                str(
                    READER_ONLINE
                    if ref_time - timestamp
                    < sql("SELECT * FROM offline_timeout").fetchone()[0] * 60
                    else READER_OFFLINE
                ),
                reader_id,
            ),
        )

    return True


def get_canvas_status():
    """
    Get the status & time of the Canvas updater
    """

    if not sql("SELECT * FROM canvas_status").fetchone():
        logger.error("No Canvas status present")
        return False

    return sql("SELECT status, timestamp FROM canvas_status").fetchone()


def set_canvas_pending():
    """
    Set Canvas status to be pending if not in progress
    """

    status, _ = get_canvas_status()

    if status == CANVAS_UPDATING:
        return False
    else:
        sql("UPDATE canvas_status SET status = ?", (str(CANVAS_PENDING)))
        return True


def set_canvas_status(status: int):
    """
    Set Canvas status to 'UPDATING' or 'OK'
    """
    get_canvas_status()
    sql("UPDATE canvas_status SET status = ?", (str(status)))

    if status == CANVAS_OK:
        sql("UPDATE canvas_status SET timestamp = ?", (time.time(),))
    return True


def get_tagout():
    if not sql("SELECT * FROM tagout").fetchone():
        logger.error("No tagout UID present")
        return False

    return sql("SELECT uid FROM tagout").fetchone()[0]


def set_tagout(uid: str):
    uid = uid.lower()

    sql("UPDATE tagout SET uid = ?", (uid,))
    return True


def get_offline_timeout():
    if not sql("SELECT * FROM offline_timeout").fetchone():
        logger.error("No offline timeout time present")
        return False

    return sql("SELECT timeout_min FROM offline_timeout").fetchone()[0]


def set_offline_timeout(timeout_min: int):
    sql("UPDATE offline_timeout SET timeout_min = ?", (str(timeout_min),))
    return True
    return True


def get_canvas_course_id():
    if not sql("SELECT * FROM canvas_course_id").fetchone():
        logger.error("No Canvas course ID present")
        return False

    return sql("SELECT id FROM canvas_course_id").fetchone()[0]


def set_canvas_course_id(id: int):
    sql("UPDATE canvas_course_id SET id = ?", (str(id),))
    return True


def evaluate_modules(completed_modules: list, cruzid: str, num_modules: int):
    """
    Evaluate the modules completed by a student and set their access statuses
    """
    if not is_student(cruzid=cruzid):
        return False

    module_data = sql("SELECT * FROM rooms").fetchall()

    for room, exp in module_data:
        exp = exp.lower().replace("and", "&").replace("or", "|").replace(" ", "")
        if not exp:
            exp = "f"

        for m in range(num_modules, 0, -1):
            exp = exp.replace(str(m), "t" if m in completed_modules else "f")

        for c in exp:
            if c not in "tf&|()":
                exp = exp.replace(c, "")

        current_access = get_access(room, cruzid=cruzid)
        if (
            current_access == ACCESS_YES_OVERRIDE
            or current_access == ACCESS_NO_OVERRIDE
        ):
            continue
        elif not set_access(
            room,
            ACCESS_YES if len(exp) > 0 and string_eval(exp) == "t" else ACCESS_NO,
            cruzid,
        ):
            return False
    return True


def string_eval(exp: str):
    """
    Evaluate a string expression for modules.

    exp: str: the expression to evaluate.

    Returns the evaluated expression.
    """

    while "(" in exp:
        start = 0
        end = exp.index(")")
        while "(" in exp[start + 1 : end]:
            start = exp.index("(", start + 1)

        exp = exp[:start] + string_eval(exp[start + 1 : end]) + exp[end + 1 :]

    while "&" in exp:
        i = exp.index("&")

        bw = 0
        if "|" in exp[:i]:
            bw = exp.rindex("|", 0, i) + 1

        fw = len(exp)
        if "|" in exp[i + 1 :]:
            fw = exp.index("|", i + 1)

        exp = (
            exp[:bw]
            + (
                "t"
                if (
                    string_eval(exp[bw:i]) == "t"
                    and string_eval(exp[i + 1 : fw]) == "t"
                )
                else "f"
            )
            + exp[fw:]
        )

    while "|" in exp:
        i = exp.index("|")
        exp = (
            exp[: i - 1]
            + (
                "t"
                if (string_eval(exp[:i]) == "t" or string_eval(exp[i + 1 :]) == "t")
                else "f"
            )
            + exp[i + 2 :]
        )

    return exp


def set_access_details(reader_id: int, room: str, color: str, alarm_delay_min: int):
    """
    Set the access details for a room
    """

    color = color.lower()

    if not is_room(room) and room not in ["staff", "no_access"]:
        logger.warning(
            f"set_access_details: Room {room} does not exist in the database"
        )
        return False
    elif not sql("SELECT * FROM readers WHERE reader_id = ?", (reader_id,)).fetchone():
        logger.warning(f"set_access_details: No reader with ID {reader_id}")
        return False
    elif any([c not in "0123456789abcdef" for c in color]):
        logger.warning(f"set_access_details: Color {color} is not a valid hex color")
        return False

    sql(
        f"UPDATE accesses SET {room} = ? WHERE reader_id = ?",
        (f"{color},{alarm_delay_min}", reader_id),
    )
    return True


def get_access_details(reader_id: int, room: str):
    """
    Get the access details for a room
    """

    if not is_room(room) and room not in ["staff", "no_access"]:
        logger.error(f"get_access_details: Room {room} does not exist in the database")
        return False
    elif not sql("SELECT * FROM readers WHERE reader_id = ?", (reader_id,)).fetchone():
        logger.error(f"get_access_details: No reader with ID {reader_id}")
        return False

    details = sql(
        f"SELECT {room} FROM accesses WHERE reader_id = ?",
        (reader_id,),
    ).fetchone()[0]

    if not details:
        return (None, None)
    else:
        details = details.split(",")
        return (details[0], int(details[1]))


def scan_uid(reader_id: int, uid: str):
    uid = uid.lower()

    if is_staff(uid=uid):
        details = get_access_details(reader_id, "staff")
        if not details:
            logger.error(
                f"scan_uid: get_access_details failed for reader {reader_id} and uid {uid} (staff)"
            )
            return False
        elif details[0]:
            return details

    elif is_student(uid=uid):
        for room in sql("SELECT name FROM rooms").fetchall():

            access = get_access(room[0], uid=uid)
            if access is False:
                logger.error(
                    f"scan_uid: get_access failed for room {room[0]} and uid {uid}"
                )
                return False
            elif access not in [ACCESS_YES, ACCESS_YES_OVERRIDE]:
                continue

            details = get_access_details(reader_id, room[0])
            if not details:
                logger.error(
                    f"scan_uid: get_access_details failed for reader {reader_id}, uid {uid}, and room {room[0]}"
                )
                return False
            elif details[0]:
                return details

    details = get_access_details(reader_id, "no_access")
    if not details:
        logger.error(
            f"scan_uid: get_access_details failed for reader {reader_id} and uid {uid} (no_access)"
        )
        return False
    return details


def get_alarm_status(reader_id: int):
    if not sql("SELECT * FROM readers WHERE reader_id = ?", reader_id).fetchone():
        logger.error(f"get_alarm_status: Reader {reader_id} does not exist in db")

    status = sql(
        "SELECT alarm_status FROM readers WHERE reader_id = ?", reader_id
    ).fetchone()
    if status is None:
        return ALARM_STATUS_OK
    return status[0]


if __name__ == "__main__":
    pass
    # remove_room("Super_User")
    # add_room("Super User", "7")

    # add_student("ewachtel", "Eliot", "Wachtel", "ASDF1234")
    # add_staff("imadan1", "Ishan", "Madan")
    # add_room("be_49", "3 & 4")

    # print(is_student(cruzid="ewachtel"))
    # print(is_student(uid="ASDF1234"))
    # print(get_uid("ewachtel"))

    # print(is_student(cruzid="imadan1"))
    # print(is_student(uid=""))
    # print(get_uid("imadan1"))

    # print(set_access("be_49", ACCESS_YES, "ewachtel"))
    # print(get_access("be_49", "ewachtel"))

    # remove_student("ewachtel")
    # remove_staff("imadan1")
    # remove_room("be_49")

    # print(add_reader("BE 51", True, 10))
    # print(get_reader_settings(0))
    # print(check_in(0))
    # print(set_reader_online_statuses())
    # print(get_reader_settings(0))
    # print(remove_reader(0))

    # print('get', get_canvas_status())
    # time.sleep(5)
    # print('pend', set_canvas_pending())
    # time.sleep(5)
    # print('up', set_canvas_status(CANVAS_UPDATING))
    # time.sleep(5)
    # print('pend', set_canvas_pending())
    # time.sleep(5)
    # print("ok", set_canvas_status(CANVAS_OK))
    # time.sleep(5)
    # print('get', get_canvas_status())

    # add_room("super_user", "7")
    # add_room("club_leadership", "9")
    # add_room("be_49", "5")
    # add_room("be_50", "6")
    # add_room("be_51", "4")
    # add_room("be_52", "")
    # add_room("be_53", "")
    # add_room("be_54", "3")
    # add_room("be_55", "")
    # add_room("bambu_printing", "13")

    # set_access("be_53", ACCESS_YES, "ewachtel")
    # print(evaluate_modules(range(1, 16, 2), "ewachtel", 15))

    # set_access("be_52", ACCESS_YES_OVERRIDE, "ewachtel")

    # print(get_user_data(cruzid="ewachtel"))
    # print(get_user_data(uid="asdf1234"))
    # print(get_user_data(cruzid="ewachtel1"))
    # print(get_user_data(cruzid="imadan1"))

    # print(set_reader_settings(0, "BE 49", False, 5))
    # print(set_reader_settings(1, "BE 49", False, 5))
    # print(set_reader_settings(0, None, None, None))
    # print(set_reader_settings(0, "", False, 0))
    # print(get_reader_settings(0))

    # print(set_access_details(0, "be_49", "112233", 20))
    # print(set_access_details(0, "staff", "ff7700", 60))

    # print(get_access_details(0, "be_51"))
    # print(get_access_details(0, "staff"))
    # print(get_access_details(0, "no_access"))

    # print(set_uid("imadan1", "ghjk5678"))

    # print(scan_uid(0, "asdf1234"))
    # print(scan_uid(0, "ghjk5678"))
    # print(scan_uid(1, "asdf1234"))
    # print(scan_uid(1, "ghjk5678"))
    # print(scan_uid(0, "abcdefgh"))

    # print(get_tagout())
    # print(get_offline_timeout())
    # print(get_canvas_course_id())
    # print(set_tagout('zxcvbnmp'))
    # print(set_offline_timeout(5))
    # print(set_canvas_course_id(67429))
