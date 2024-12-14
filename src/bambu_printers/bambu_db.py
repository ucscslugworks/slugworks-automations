import json
import os
import sqlite3
import time
import traceback
from datetime import datetime

from src import constants, log


def get_sqlite3_thread_safety():

    # Map value from SQLite's THREADSAFE to Python's DBAPI 2.0
    # threadsafety attribute.
    sqlite_threadsafe2python_dbapi = {0: 0, 2: 1, 1: 3}
    conn = sqlite3.connect(":memory:")
    threadsafety = conn.execute(
        """
select * from pragma_compile_options
where compile_options like 'THREADSAFE=%'
"""
    ).fetchone()[0]
    conn.close()

    threadsafety_value = int(threadsafety.split("=")[1])

    return sqlite_threadsafe2python_dbapi[threadsafety_value]


if sqlite3.threadsafety == 3 or get_sqlite3_thread_safety() == 3:
    check_same_thread = False
else:
    check_same_thread = True

db = sqlite3.connect(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "bambu.db"),
    autocommit=True,
    check_same_thread=check_same_thread,
    isolation_level=None,
)
db.execute("PRAGMA journal_mode=WAL")
cursor = db.cursor()
sql = cursor.execute

CREATE_TABLES = {
    "prints_unmatched": [
        "id INTEGER PRIMARY KEY",
        "printer TEXT",
        "title TEXT",
        "cover TEXT",
        "start_time INTEGER",
        "end_time INTEGER",
        "weight INTEGER",
        "color1 TEXT",
        "color1_weight INTEGER",
        "color2 TEXT",
        "color2_weight INTEGER",
        "color3 TEXT",
        "color3_weight INTEGER",
        "color4 TEXT",
        "color4_weight INTEGER",
    ],
    "prints_current": [
        "id INTEGER PRIMARY KEY",
        "form_row INTEGER",
        "cruzid TEXT",
        "printer TEXT",
        "title TEXT",
        "cover TEXT",
        "start_time INTEGER",
        "end_time INTEGER",
        "weight INTEGER",
        "color1 TEXT",
        "color1_weight INTEGER",
        "color2 TEXT",
        "color2_weight INTEGER",
        "color3 TEXT",
        "color3_weight INTEGER",
        "color4 TEXT",
        "color4_weight INTEGER",
    ],
    "prints_archive": [
        "id INTEGER PRIMARY KEY",
        "status INTEGER",
        "form_row INTEGER",
        "cruzid TEXT",
        "printer TEXT",
        "title TEXT",
        "cover TEXT",
        "start_time INTEGER",
        "end_time INTEGER",
        "weight INTEGER",
        "color1 TEXT",
        "color1_weight INTEGER",
        "color2 TEXT",
        "color2_weight INTEGER",
        "color3 TEXT",
        "color3_weight INTEGER",
        "color4 TEXT",
        "color4_weight INTEGER",
    ],
    "form_unmatched": [
        "form_row INTEGER PRIMARY KEY",
        "timestamp INTEGER",
        "printer TEXT",
        "cruzid TEXT",
    ],
    "form_archive": [
        "form_row INTEGER PRIMARY KEY",
        "print_id INTEGER",
        "timestamp INTEGER",
        "printer TEXT",
        "cruzid TEXT",
    ],
    "limits": [
        "cruzid TEXT PRIMARY KEY",
    ],
    "printers": [
        "name TEXT PRIMARY KEY",
        "status INTEGER",
        "last_update INTEGER",
        "print_id INTEGER",
        "cruzid TEXT",
        "gcode_state INTEGER",
        "tool_temp REAL",
        "tool_temp_target REAL",
        "bed_temp REAL",
        "bed_temp_target REAL",
        "fan_speed INTEGER",
        "speed_level INTEGER",
        "light_state INTEGER",
        "current_stage TEXT",
        "gcode_file TEXT",
        "layer_count INTEGER",
        "current_layer INTEGER",
        "percent_complete INTEGER",
        "time_remaining INTEGER",
        "start_time INTEGER",
        "end_time INTEGER",
        "active_spool INTEGER",
        "spool_state INTEGER",
    ],
}

DATA_TABLES = {
    name: [col.split(" ")[0] for col in CREATE_TABLES[name]] for name in CREATE_TABLES
}

EXEMPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "common",
    "bambu_limit_exempt.json",
)

DB_OBJECT = None
DB_STARTED = False


def get_db():
    global DB_OBJECT, DB_STARTED

    if not DB_STARTED:
        DB_STARTED = True
        DB_OBJECT = BambuDB()
        DB_OBJECT.logger.info("get_db: Created new DB object")
    else:
        while DB_OBJECT is None:
            time.sleep(1)

        DB_OBJECT.logger.info("get_db: Retrieved existing DB object")

    return DB_OBJECT


class BambuDB:
    def __init__(self):
        try:
            self.logger = log.setup_logs(
                "bambu_db", additional_handlers=[("bambu", log.INFO)]
            )
            for name in CREATE_TABLES:
                sql(
                    f"CREATE TABLE IF NOT EXISTS {name} ({', '.join(CREATE_TABLES[name])})"
                )

            self.column = self.get_limits_column()
            self.logger.info("init: Initialized")
        except Exception:
            self.logger.error(f"init: {traceback.format_exc()}")
            exit(1)

    def add_print(
        self,
        id: int,
        printer: str,
        title: str,
        cover: str,
        start_time: int,
        end_time: int,
        weight: int,
        color1: str,
        color1_weight: int,
        color2: str,
        color2_weight: int,
        color3: str,
        color3_weight: int,
        color4: str,
        color4_weight: int,
    ):
        try:
            sql(
                f"INSERT INTO prints_unmatched ({', '.join(DATA_TABLES['prints_unmatched'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['prints_unmatched']))})",
                (
                    id,
                    printer,
                    title,
                    cover,
                    start_time,
                    end_time,
                    weight,
                    color1,
                    color1_weight,
                    color2,
                    color2_weight,
                    color3,
                    color3_weight,
                    color4,
                    color4_weight,
                ),
            )
            self.logger.info(f"add_print: Added print {id}")
            self.update_printer(
                printer, status=constants.PRINTER_UNMATCHED, print_id=id, cruzid=""
            )
            self.logger.info(
                f"add_print: Updated printer {printer} - UNMATCHED, print {id}"
            )
            return True
        except Exception:
            self.logger.error(f"add_print: {traceback.format_exc()}")
            return False

    def add_form(self, form_row: int, timestamp: int, printer: str, cruzid: str):
        try:
            sql(
                f"INSERT INTO form_unmatched ({', '.join(DATA_TABLES['form_unmatched'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['form_unmatched']))})",
                (form_row, timestamp, printer, cruzid),
            )
            self.logger.info(f"add_form: Added form {form_row}")
            return True
        except Exception:
            self.logger.error(f"add_form: {traceback.format_exc()}")
            return False

    def match(self, print_id: int, form_row: int):
        try:
            print_data = sql(
                "SELECT * FROM prints_unmatched WHERE id = ?", (print_id,)
            ).fetchone()
            if not print_data:
                self.logger.warning(f"match: Print {print_id} not found")
                return False

            form_data = None

            if form_row != -1:
                form_data = sql(
                    "SELECT * FROM form_unmatched WHERE form_row = ?", (form_row,)
                ).fetchone()
                if not form_data:
                    self.logger.warning(f"match: Form {form_row} not found")
                    return False

            sql(
                f"INSERT INTO prints_current ({', '.join(DATA_TABLES['prints_current'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['prints_current']))})",
                (
                    print_id,
                    form_row,
                    "" if not form_data else form_data[3],
                    *print_data[1:],
                ),
            )

            self.logger.info(
                f"match: Updated printer {print_data[1]} - MATCHED, print {print_id}, cruzid '{'' if not form_data else form_data[3]}'"
            )

            if form_row != -1 and form_data:
                sql(
                    f"INSERT INTO form_archive ({', '.join(DATA_TABLES['form_archive'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['form_archive']))})",
                    (form_row, print_id, *form_data[1:]),
                )

            sql("DELETE FROM prints_unmatched WHERE id = ?", (print_id,))

            if form_row != -1:
                sql("DELETE FROM form_unmatched WHERE form_row = ?", (form_row,))

            self.logger.info(f"match: Matched print {print_id} with form {form_row}")
            return True
        except Exception:
            self.logger.error(f"match: {traceback.format_exc()}")
            return False

    def expire_print(self, print_id: int):
        try:
            print_data = sql(
                "SELECT * FROM prints_unmatched WHERE id = ?", (print_id,)
            ).fetchone()

            if not print_data:
                self.logger.warning(f"expire_print: Print {print_id} not found")
                return False

            sql("DELETE FROM prints_unmatched WHERE id = ?", (print_id,))

            sql(
                f"INSERT INTO prints_archive ({', '.join(DATA_TABLES['prints_archive'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['prints_archive']))})",
                (
                    print_id,
                    constants.PRINT_EXPIRED,
                    constants.NO_FORM_ROW,
                    constants.NO_CRUZID,
                    *print_data[1:],
                ),
            )

            self.logger.info(f"expire_print: Archived print {print_id} as expired")
            return True
        except Exception:
            self.logger.error(f"expire_print: {traceback.format_exc()}")
            return False

    def archive_print(self, print_id: int, status: int):
        try:
            print_data = sql(
                "SELECT * FROM prints_current WHERE id = ?", (print_id,)
            ).fetchone()

            if not print_data:
                self.logger.warning(f"archive_print: Print {print_id} not found")
                return False

            sql("DELETE FROM prints_current WHERE id = ?", (print_id,))

            sql(
                f"INSERT INTO prints_archive ({', '.join(DATA_TABLES['prints_archive'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['prints_archive']))})",
                (print_id, status, *print_data[1:]),
            )

            self.logger.info(
                f"archive_print: Archived print {print_id} as status {status}"
            )
            return True
        except Exception:
            self.logger.error(f"archive_print: {traceback.format_exc()}")
            return False

    def expire_form(self, form_row: int):
        try:
            form_data = sql(
                "SELECT * FROM form_unmatched WHERE form_row = ?", (form_row,)
            ).fetchone()

            if not form_data:
                self.logger.warning(f"expire_form: Form {form_row} not found")
                return False

            sql("DELETE FROM form_unmatched WHERE form_row = ?", (form_row,))

            sql(
                f"INSERT INTO form_archive ({', '.join(DATA_TABLES['form_archive'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['form_archive']))})",
                (
                    form_row,
                    constants.NO_PRINT_ID,
                    *form_data[1:],
                ),
            )

            self.logger.info(f"expire_form: Archived form {form_row} as expired")
            return True
        except Exception:
            self.logger.error(f"match: {traceback.format_exc()}")
            return False

    def get_unmatched_prints(self):
        try:
            return sql("SELECT * FROM prints_unmatched").fetchall()
        except Exception:
            self.logger.error(f"get_unmatched_prints: {traceback.format_exc()}")
            return []

    def get_current_prints(self):
        try:
            return sql("SELECT * FROM prints_current").fetchall()
        except Exception:
            self.logger.error(f"get_current_prints: {traceback.format_exc()}")
            return []

    def get_unmatched_forms(self):
        try:
            return sql("SELECT * FROM form_unmatched").fetchall()
        except Exception:
            self.logger.error(f"get_unmatched_forms: {traceback.format_exc()}")
            return []

    def get_limit(self, cruzid: str):
        try:
            if cruzid in json.load(
                open(
                    EXEMPT_PATH,
                    "r",
                )
            ):
                self.logger.info(f"get_limit: Exempted user {cruzid}")
                return constants.BAMBU_EXEMPT_LIMIT

            self.column = self.get_limits_column()

            if self.column not in [
                p[0]
                for p in sql("SELECT name from pragma_table_info('limits')").fetchall()
            ]:
                sql(f"ALTER TABLE limits ADD COLUMN {self.column} REAL")

            result = sql(
                f"SELECT {self.column} FROM limits WHERE cruzid = ?",
                (cruzid,),
            ).fetchone()

            if not result:
                sql(
                    f"INSERT INTO limits ({', '.join(DATA_TABLES['limits'])}, {self.column}) VALUES ({', '.join(['?'] * len(DATA_TABLES['limits']))}, ?)",
                    (cruzid, constants.BAMBU_DEFAULT_LIMIT),
                )
                self.logger.info(f"get_limit: Added limit for {cruzid} ({self.column})")
                return constants.BAMBU_DEFAULT_LIMIT
            elif result[0] is None:
                sql(
                    f"UPDATE limits SET {self.column} = ? WHERE cruzid = ?",
                    (constants.BAMBU_DEFAULT_LIMIT, cruzid),
                )
                self.logger.info(
                    f"get_limit: Added limit for {cruzid} for {self.column}"
                )
                return constants.BAMBU_DEFAULT_LIMIT

            self.logger.info(f"get_limit: Retrieved limit {result[0]} for {cruzid}")
            return result[0]
        except Exception:
            self.logger.error(f"get_limit: {traceback.format_exc()}")
            return None

    def subtract_limit(self, cruzid: str, amount: float):
        try:
            self.logger.info(f"subtract_limit: Subtracting {amount} from {cruzid}")
            old_limit = self.get_limit(cruzid)
            if old_limit is not None and old_limit < constants.BAMBU_DEFAULT_LIMIT:
                amount = max(amount, old_limit - constants.BAMBU_DEFAULT_LIMIT)
                self.logger.info(
                    f"subtract_limit: Adjusted amount to {amount} to not exceed default limit"
                )

            if cruzid in json.load(
                open(
                    EXEMPT_PATH,
                    "r",
                )
            ):
                self.logger.info(f"subtract_limit: Exempted user {cruzid}")
                return True

            sql(
                f"UPDATE limits SET {self.column} = {self.column} - ? WHERE cruzid = ?",
                (amount, cruzid),
            )

            self.logger.info(
                f"subtract_limit: Subtracted {amount} from {cruzid} for {self.column}"
            )
            return True
        except Exception:
            self.logger.error(f"subtract_limit: {traceback.format_exc()}")
            return False

    def print_exists(self, print_id: int):
        try:
            return (
                bool(
                    sql(
                        "SELECT * FROM prints_unmatched WHERE id = ?", (print_id,)
                    ).fetchone()
                )
                or bool(
                    sql(
                        "SELECT * FROM prints_current WHERE id = ?", (print_id,)
                    ).fetchone()
                )
                or bool(
                    sql(
                        "SELECT * FROM prints_archive WHERE id = ?", (print_id,)
                    ).fetchone()
                )
            )
        except Exception:
            self.logger.error(f"print_exists: {traceback.format_exc()}")
            return False

    def form_exists(self, form_row: int):
        try:
            return bool(
                sql(
                    "SELECT * FROM form_unmatched WHERE form_row = ?", (form_row,)
                ).fetchone()
            ) or bool(
                sql(
                    "SELECT * FROM form_archive WHERE form_row = ?", (form_row,)
                ).fetchone()
            )
        except Exception:
            self.logger.error(f"form_exists: {traceback.format_exc()}")
            return False

    def get_limits_column(self):
        return f"weight_{datetime.now().year}_{(datetime.now().month - 1) // 3}"

    def update_print_end_time(self, print_id: int, end_time: int):
        try:
            sql(
                "UPDATE prints_current SET end_time = ? WHERE id = ?",
                (end_time, print_id),
            )
            self.logger.info(
                f"update_print_end_time: Updated print {print_id} end time to {end_time}"
            )
            return True
        except Exception:
            self.logger.error(f"update_print_end_time: {traceback.format_exc()}")
            return False

    def add_printer(self, name: str):
        try:
            if sql("SELECT * FROM printers WHERE name = ?", (name,)).fetchone():
                self.logger.warning(f"add_printer: Printer {name} already exists")
                return False

            sql(
                f"INSERT INTO printers ({', '.join(DATA_TABLES['printers'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['printers']))})",
                (
                    name,  # name
                    constants.PRINTER_OFFLINE,  # status
                    -1,  # last_update
                    -1,  # print_id
                    constants.NO_CRUZID,  # cruzid
                    constants.GCODE_UNKNOWN,  # gcode_state
                    -1,  # tool_temp
                    -1,  # tool_temp_target
                    -1,  # bed_temp
                    -1,  # bed_temp_target
                    -1,  # fan_speed
                    -1,  # speed_level
                    -1,  # light_state
                    "",  # current_stage
                    "",  # gcode_file
                    -1,  # layer_count
                    -1,  # current_layer
                    -1,  # percent_complete
                    -1,  # time_remaining
                    -1,  # start_time
                    -1,  # end_time
                    -1,  # active_spool
                    -1,  # spool_state
                ),
            )
            self.logger.info(f"add_printer: Added printer {name}")
            return True
        except Exception:
            self.logger.error(f"add_printer: {traceback.format_exc()}")
            return False

    def update_printer(self, name: str, **kwargs):
        try:
            if not sql("SELECT * FROM printers WHERE name = ?", (name,)).fetchone():
                self.logger.warning(f"update_printer: Printer {name} not found")
                return False

            sql(
                f"UPDATE printers SET {', '.join([f'{k} = ?' for k in kwargs])} WHERE name = ?",
                (*kwargs.values(), name),
            )
            self.logger.info(f"update_printer: Updated printer {name}")
            return True
        except Exception:
            self.logger.error(f"update_printer: {traceback.format_exc()}")
            return False

    def get_printer_data(self, name: str):
        try:
            data = sql(
                f"SELECT {', '.join(DATA_TABLES['printers'])} FROM printers WHERE name = ?",
                (name,),
            ).fetchone()

            if not data:
                self.logger.warning(f"get_printer_data: Printer {name} not found")
                return None

            return {label: data[i] for i, label in enumerate(DATA_TABLES["printers"])}
        except Exception:
            self.logger.error(f"get_printer_data: {traceback.format_exc()}")
            return None

    def get_printer_list(self):
        try:
            return sql("SELECT name FROM printers").fetchall()
        except Exception:
            self.logger.error(f"get_printer_list: {traceback.format_exc()}")
            return []

    def check_offline_printers(self):
        try:
            for printer, last_update in sql("SELECT name FROM printers").fetchall():
                if last_update < time.time() - constants.BAMBU_OFFLINE_TIMEOUT:
                    self.logger.warning(
                        f"check_offline_printers: Printer {printer} offline"
                    )
                    sql(
                        "UPDATE printers SET status = ? WHERE name = ?",
                        (constants.PRINTER_OFFLINE, printer),
                    )
        except Exception:
            self.logger.error(f"check_offline_printers: {traceback.format_exc()}")
