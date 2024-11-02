import os
import sqlite3
import time

from src import constants, log

# Change directory to repository root
# path = os.path.abspath(
#     os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
# )
os.chdir(os.path.abspath(__file__))


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

db = sqlite3.connect("bambu.db", autocommit=True, check_same_thread=check_same_thread)
cursor = db.cursor()
sql = cursor.execute

CREATE_TABLES = [
    (
        "prints_unmatched",
        "(id INTEGER PRIMARY KEY, printer TEXT, title TEXT, cover TEXT, start_time INTEGER, end_time INTEGER, weight INTEGER, color1 TEXT, color1_weight INTEGER, color2 TEXT, color2_weight INTEGER, color3 TEXT, color3_weight INTEGER, color4 TEXT, color4_weight INTEGER)",
    ),
    ("prints_current", "(name TEXT, modules_expr TEXT)"),
    ("prints_archive", "(reader_id INTEGER, staff TEXT, no_access TEXT)"),
    ("form_unmatched", "(cruzid TEXT, firstname TEXT, lastname TEXT, uid TEXT)"),
    ("form_archive", "(status INTEGER, timestamp REAL)"),
]

for name, params in CREATE_TABLES:
    sql(f"CREATE TABLE IF NOT EXISTS {name} {params}")
