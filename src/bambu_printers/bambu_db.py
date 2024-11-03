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
        "weight REAL",
    ],
}

DATA_TABLES = {
    name: [col.split(" ")[0] for col in CREATE_TABLES[name]] for name in CREATE_TABLES
}


class BambuDB:
    def __init__(self):
        self.logger = log.setup_logs("bambu_db")

        try:
            for name in CREATE_TABLES:
                sql(
                    f"CREATE TABLE IF NOT EXISTS {name} ({', '.join(CREATE_TABLES[name])})"
                )

            self.logger.info("Initialized")
        except Exception as e:
            self.logger.error(f"init: {e}")
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
            self.logger.info(f"Added print {id}")
            return True
        except Exception as e:
            self.logger.error(f"add_print: {e}")
            return False

    def add_form(self, form_row: int, timestamp: int, printer: str, cruzid: str):
        try:
            sql(
                f"INSERT INTO form_unmatched ({', '.join(DATA_TABLES['form_unmatched'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['form_unmatched']))})",
                (form_row, timestamp, printer, cruzid),
            )
            self.logger.info(f"Added form {form_row}")
            return True
        except Exception as e:
            self.logger.error(f"add_form: {e}")
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
                (print_id, form_row, *print_data[1:]),
            )

            sql(
                f"INSERT INTO form_archive ({', '.join(DATA_TABLES['form_archive'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['form_archive']))})",
                (form_row, print_id, *form_data[1:]),
            )

            sql("DELETE FROM prints_unmatched WHERE id = ?", (print_id,))
            sql("DELETE FROM form_unmatched WHERE form_row = ?", (form_row,))

            self.logger.info(f"Matched print {print_id} with form {form_row}")
            return True
        except Exception as e:
            self.logger.error(f"match: {e}")
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
                    *print_data[1:],
                ),
            )

            self.logger.info(f"Archived print {print_id} as expired")
            return True
        except Exception as e:
            self.logger.error(f"expire_print: {e}")
            return False

    def archive_print(self, print_id: int, status: int):
        try:
            print_data = sql(
                "SELECT * FROM prints_cuarchiveHERE id = ?", (print_id,)
            ).fetchone()

            if not print_data:
                self.logger.warning(f"archive_print: Print {print_id} not found")
                return False

            sql("DELETE FROM prints_current WHERE id = ?", (print_id,))

            sql(
                f"INSERT INTO prints_current ({', '.join(DATA_TABLES['prints_current'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['prints_current']))})",
                (print_id, status, *print_data[1:]),
            )

            self.logger.info(f"Archived print {print_id} as status {status}")
            return True
        except Exception as e:
            self.logger.error(f"archive_print: {e}")
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

            self.logger.info(f"Archived form {form_row} as expired")
            return True
        except Exception as e:
            self.logger.error(f"match: {e}")
            return False

    def get_unmatched_prints(self):
        try:
            return sql("SELECT * FROM prints_unmatched").fetchall()
        except Exception as e:
            self.logger.error(f"get_unmatched_prints: {e}")
            return []

    def get_current_prints(self):
        try:
            return sql("SELECT * FROM prints_current").fetchall()
        except Exception as e:
            self.logger.error(f"get_current_prints: {e}")
            return []

    def get_unmatched_forms(self):
        try:
            return sql("SELECT * FROM form_unmatched").fetchall()
        except Exception as e:
            self.logger.error(f"get_unmatched_forms: {e}")
            return []

    def get_limit(self, cruzid: str):
        try:
            result = sql("SELECT * FROM limits WHERE cruzid = ?", (cruzid,)).fetchone()

            if not result:
                sql(
                    f"INSERT INTO limits ({', '.join(DATA_TABLES['limits'])}) VALUES ({', '.join(['?'] * len(DATA_TABLES['limits']))})",
                    (cruzid, constants.BAMBU_DEFAULT_LIMIT),
                )
                return constants.BAMBU_DEFAULT_LIMIT

            return result[1]
        except Exception as e:
            self.logger.error(f"get_limit: {e}")
            return []

    def subtract_limit(self, cruzid: str, amount: float):
        try:
            sql(
                "UPDATE limits SET weight = weight - ? WHERE cruzid = ?",
                (amount, cruzid),
            )
            return True
        except Exception as e:
            self.logger.error(f"subtract_limit: {e}")
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
            self.logger.error(f"print_exists: {e}")
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
            self.logger.error(f"form_exists: {e}")
            return False
