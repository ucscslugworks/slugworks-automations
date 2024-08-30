import datetime
import logging
import os
import sqlite3
import time

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

# Create a new directory for logs if it doesn't exist
if not os.path.exists(path + "/logs/server"):
    os.makedirs(path + "/logs/server")

# create new logger with all levels
logger = logging.getLogger("root")
logger.setLevel(logging.DEBUG)

# create file handler which logs debug messages (and above - everything)
fh = logging.FileHandler(f"logs/server/{str(datetime.datetime.now())}.log")
fh.setLevel(logging.DEBUG)

# create console handler which only logs warnings (and above)
ch = logging.StreamHandler()
ch.setLevel(logging.WARNING)

# create formatter and add it to the handlers
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s: %(message)s")
fh.setFormatter(formatter)
ch.setFormatter(formatter)

# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)

db = sqlite3.connect("src/server/access.db", autocommit=True)
cursor = db.cursor()
sql = cursor.execute

create_tables = [
    ("students", "(cruzid TEXT, firstname TEXT, lastname TEXT, uid TEXT)"),
    ("staff", "(cruzid TEXT, firstname TEXT, lastname TEXT, uid TEXT)"),
    ("rooms", "(name TEXT, modules_expr TEXT)"),
    ("accesses", "(reader_id INTEGER, staff INTEGER, no_access INTEGER)"),
    (
        "readers",
        "(reader_id INTEGER, online INTEGER, location TEXT, alarm_enable INTEGER, alarm_delay_min INTEGER, alarm_status INTEGER, last_seen REAL)",
    ),
    ("canvas_status", "(status INTEGER, timestamp REAL)"),
]

for name, params in create_tables:
    sql(f"CREATE TABLE IF NOT EXISTS {name} {params}")

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
    elif any([not c.isalpha() and c != " " for c in firstname]):
        logger.warning(f"add_student: First name {firstname} is not alphabetic")
        return False
    elif any([not c.isalpha() and c != " " for c in lastname]):
        logger.warning(f"add_student: Last name {lastname} is not alphabetic")
        return False
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
    return True


def is_student(cruzid: str | None = None, uid: str | None = None):
    """
    Check if a given cruzid or uid belongs to a student in the database
    """

    if uid:
        uid = uid.lower()

    return bool(
        (
            cruzid
            and sql("SELECT * FROM students WHERE cruzid = ?", (cruzid,)).fetchone()
        )
        or (uid and sql("SELECT * FROM students WHERE uid = ?", (uid,)).fetchone())
    )


def add_staff(cruzid: str, firstname: str, lastname: str, uid: str | None = None):
    """
    Add a new staff member to the database
    """
    if uid is None:
        uid = ""

    if not cruzid.isalnum():
        logger.warning(f"add_student: Student {cruzid} is not alphanumeric")
        return False
    elif any([not c.isalpha() and c != " " for c in firstname]):
        logger.warning(f"add_student: First name {firstname} is not alphabetic")
        return False
    elif any([not c.isalpha() and c != " " for c in lastname]):
        logger.warning(f"add_student: Last name {lastname} is not alphabetic")
        return False
    elif not uid.isalnum() and uid != "":
        logger.warning(f"add_student: UID {uid} is not alphanumeric")
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

    if uid:
        uid = uid.lower()

    return bool(
        (cruzid and sql("SELECT * FROM staff WHERE cruzid = ?", (cruzid,)).fetchone())
        or (uid and sql("SELECT * FROM staff WHERE uid = ?", (uid,)).fetchone())
    )


def user_exists(cruzid: str | None = None, uid: str | None = None):
    """
    Call both is_student and is_staff - does a user with the given details exist
    """
    return is_student(cruzid=cruzid, uid=uid) or is_staff(cruzid=cruzid, uid=uid)


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


def get_access(room: str, cruzid: str):
    if not is_room(room) or not is_student(cruzid=cruzid):
        return False

    print(sql(f"SELECT {room} FROM students WHERE cruzid = ?", (cruzid,)).fetchone())


def add_room(name: str, modules_expr: str):
    """
    Add a new room
    """
    name = name.strip().replace(" ", "_")

    if any([not c.isalnum() and c != "_" for c in name]):
        logger.warning(f"add_room: Room {name} is not alphanumeric")
        return False

    if sql("SELECT * FROM rooms WHERE name = ?", (name,)).fetchone():
        logger.warning(f"add_room: Room {name} already exists in the database")
        return False

    sql(
        "INSERT INTO rooms (name, modules_expr) VALUES (?, ?)",
        (name, modules_expr),
    )
    sql(f"ALTER TABLE accesses ADD COLUMN {name} INTEGER")
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
            ALARM_STATUS_TAGGEDOUT,
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
                    READER_ONLINE if ref_time - timestamp < 15 * 60 else READER_OFFLINE
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
        sql(
            "INSERT INTO canvas_status (status, timestamp) VALUES (?, ?)",
            (str(CANVAS_PENDING), -1),
        )

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


if __name__ == "__main__":
    pass
    # remove_room("Super_User")
    # add_room("Super User", "7")

    add_student("ewachtel", "Eliot", "Wachtel", "ASDF1234")
    add_staff("imadan1", "Ishan", "Madan")
    add_room("be_49", "3 & 4")

    # print(is_student(cruzid="ewachtel"))
    # print(is_student(uid="ASDF1234"))
    # print(get_uid("ewachtel"))

    # print(is_student(cruzid="imadan1"))
    # print(is_student(uid=""))
    # print(get_uid("imadan1"))

    print(set_access("be_49", ACCESS_YES, "ewachtel"))
    print(get_access("be_49", "ewachtel"))

    remove_student("ewachtel")
    remove_staff("imadan1")
    remove_room("be_49")

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
