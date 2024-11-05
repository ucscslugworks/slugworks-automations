from datetime import datetime
import json
import os
import sqlite3

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
)
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


class BambuDB:
    def __init__(self):
        try:
            self.logger = log.setup_logs("bambu_db")
            for name in CREATE_TABLES:
                sql(
                    f"CREATE TABLE IF NOT EXISTS {name} ({', '.join(CREATE_TABLES[name])})"
                )

            self.column = self.get_limits_column()
            self.logger.info("init: Initialized")
        except Exception as e:
            self.logger.error(f"init: {type(e)} {e}")
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
            return True
        except Exception as e:
            self.logger.error(f"add_print: {type(e)} {e}")
            return False

    def add_form(self, form_row: int, timestamp: int, printer: str, cruzid: str):
        try:
            sql(
                f"INSERT INTO form_unmatched ({', '.join(DATA_TABLES['form_unmatched'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['form_unmatched']))})",
                (form_row, timestamp, printer, cruzid),
            )
            self.logger.info(f"add_form: Added form {form_row}")
            return True
        except Exception as e:
            self.logger.error(f"add_form: {type(e)} {e}")
            return False

    def match(self, print_id: int, form_row: int):
        try:
            print_data = sql(
                "SELECT * FROM prints_unmatched WHERE id = ?", (print_id,)
            ).fetchone()

            form_data = sql(
                "SELECT * FROM form_unmatched WHERE form_row = ?", (form_row,)
            ).fetchone()

            if not print_data or not form_data:
                self.logger.warning(
                    f"match: Print {print_id} or form {form_row} not found"
                )
                return False

            sql(
                f"INSERT INTO prints_current ({', '.join(DATA_TABLES['prints_current'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['prints_current']))})",
                (print_id, form_row, form_data[3], *print_data[1:]),
            )

            sql(
                f"INSERT INTO form_archive ({', '.join(DATA_TABLES['form_archive'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['form_archive']))})",
                (form_row, print_id, *form_data[1:]),
            )

            sql("DELETE FROM prints_unmatched WHERE id = ?", (print_id,))
            sql("DELETE FROM form_unmatched WHERE form_row = ?", (form_row,))

            self.logger.info(f"match: Matched print {print_id} with form {form_row}")
            return True
        except Exception as e:
            self.logger.error(f"match: {type(e)} {e}")
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
        except Exception as e:
            self.logger.error(f"expire_print: {type(e)} {e}")
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
        except Exception as e:
            self.logger.error(f"archive_print: {type(e)} {e}")
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
        except Exception as e:
            self.logger.error(f"match: {type(e)} {e}")
            return False

    def get_unmatched_prints(self):
        try:
            return sql("SELECT * FROM prints_unmatched").fetchall()
        except Exception as e:
            self.logger.error(f"get_unmatched_prints: {type(e)} {e}")
            return []

    def get_current_prints(self):
        try:
            return sql("SELECT * FROM prints_current").fetchall()
        except Exception as e:
            self.logger.error(f"get_current_prints: {type(e)} {e}")
            return []

    def get_unmatched_forms(self):
        try:
            return sql("SELECT * FROM form_unmatched").fetchall()
        except Exception as e:
            self.logger.error(f"get_unmatched_forms: {type(e)} {e}")
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
        except Exception as e:
            self.logger.error(f"get_limit: {type(e)} {e}")
            return None

    def subtract_limit(self, cruzid: str, amount: float):
        try:
            self.get_limit(cruzid)

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
        except Exception as e:
            self.logger.error(f"subtract_limit: {type(e)} {e}")
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
        except Exception as e:
            self.logger.error(f"print_exists: {type(e)} {e}")
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
        except Exception as e:
            self.logger.error(f"form_exists: {type(e)} {e}")
            return False

    def get_limits_column(self):
        return f"weight_{datetime.now().year}_{datetime.now().month // 4 + 1}"
