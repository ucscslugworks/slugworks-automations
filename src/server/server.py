import datetime
import logging
import os
import sqlite3

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

create_tables = [
    ("students", "(cruzid TEXT, firstname TEXT, lastname TEXT, uid TEXT)"),
    ("staff", "(cruzid TEXT, firstname TEXT, lastname TEXT, uid TEXT)"),
    ("rooms", "(name TEXT, modules_expr TEXT)"),
    ("accesses", "(reader_id INTEGER, staff TEXT, no_access TEXT)"),
    (
        "readers",
        "(reader_id INTEGER, online INTEGER, location TEXT, alarm_enable INTEGER, alarm_delay_min INTEGER, alarm_status INTEGER, last_seen REAL)",
    ),
    ("canvas_status", "(status INTEGER, timestamp REAL)"),
]

for name, params in create_tables:
    cursor.execute("CREATE TABLE IF NOT EXISTS " + name + " " + params)

# TODO: should access logs be stored in a database or in a .log file?


def add_student(cruzid: str, firstname: str, lastname: str, uid: str | None = None):
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
    elif not uid.isalnum():
        logger.warning(f"add_student: UID {uid} is not alphanumeric")
        return False

    if cursor.execute("SELECT * FROM students WHERE cruzid = ?", (cruzid,)).fetchone():
        logger.warning(f"add_student: Student {cruzid} already exists in the database")
        return False
    elif cursor.execute("SELECT * FROM staff WHERE cruzid = ?", (cruzid,)).fetchone():
        logger.warning(
            f"add_student: Student {cruzid} already exists as staff in the database"
        )
        return False

    cursor.execute(
        "INSERT INTO students (cruzid, firstname, lastname, uid) VALUES (?, ?, ?, ?)",
        (cruzid, firstname, lastname, uid),
    )
    logger.info(f"add_student: Added student {cruzid} to the database")
    return True


def remove_student(cruzid: str):
    if not cruzid.isalnum():
        logger.warning(f"remove_student: Student {cruzid} is not alphanumeric")
        return False

    if not cursor.execute(
        "SELECT * FROM students WHERE cruzid = ?", (cruzid,)
    ).fetchone():
        logger.warning(
            f"remove_student: Student {cruzid} does not exist in the database"
        )
        return False

    cursor.execute("DELETE FROM students WHERE cruzid = ?", (cruzid,))
    logger.info(f"remove_student: Removed student {cruzid} from the database")
    return True


def add_staff(cruzid: str, firstname: str, lastname: str, uid: str | None = None):
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
    elif not uid.isalnum():
        logger.warning(f"add_student: UID {uid} is not alphanumeric")
        return False

    if cursor.execute("SELECT * FROM staff WHERE cruzid = ?", (cruzid,)).fetchone():
        logger.warning(f"add_staff: Staff {cruzid} already exists in the database")
        return False
    elif cursor.execute(
        "SELECT * FROM students WHERE cruzid = ?", (cruzid,)
    ).fetchone():
        logger.warning(
            f"add_staff: Staff {cruzid} already exists as student in the database"
        )
        return False

    cursor.execute(
        "INSERT INTO staff (cruzid, firstname, lastname, uid) VALUES (?, ?, ?, ?)",
        (cruzid, firstname, lastname, uid),
    )
    logger.info(f"add_staff: Added staff {cruzid} to the database")
    return True


def remove_staff(cruzid: str):
    if not cruzid.isalnum():
        logger.warning(f"remove_staff: Staff {cruzid} is not alphanumeric")
        return False

    if not cursor.execute("SELECT * FROM staff WHERE cruzid = ?", (cruzid,)).fetchone():
        logger.warning(f"remove_staff: Staff {cruzid} does not exist in the database")
        return False

    cursor.execute("DELETE FROM staff WHERE cruzid = ?", (cruzid,))
    logger.info(f"remove_staff: Removed staff {cruzid} from the database")
    return True


def add_room(name: str, modules_expr: str):
    name = name.strip().replace(" ", "_")

    if any([not c.isalnum() and c != "_" for c in name]):
        logger.warning(f"add_room: Room {name} is not alphanumeric")
        return False

    if cursor.execute("SELECT * FROM rooms WHERE name = ?", (name,)).fetchone():
        logger.warning(f"add_room: Room {name} already exists in the database")
        return False

    cursor.execute(
        "INSERT INTO rooms (name, modules_expr) VALUES (?, ?)",
        (name, modules_expr),
    )
    cursor.execute("ALTER TABLE accesses ADD COLUMN " + name + " TEXT")
    logger.info(f"add_room: Added room {name} to the database")
    return True


def remove_room(name: str):
    if any([not c.isalnum() and c != "_" for c in name]):
        logger.warning(f"remove_room: Room {name} is not alphanumeric")
        return False

    if not cursor.execute("SELECT * FROM rooms WHERE name = ?", (name,)).fetchone():
        logger.warning(f"remove_room: Room {name} does not exist in the database")
        return False

    cursor.execute("ALTER TABLE accesses DROP COLUMN " + name)
    logger.info(f"remove_room: Removed room {name} from the database")
    return True


if __name__ == "__main__":
    remove_room("Super_User")
    add_room("Super User", "7")
