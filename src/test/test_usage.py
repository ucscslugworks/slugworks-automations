import datetime
from src.bambu_printers import get_db
from src.bambu_printers.bambu_db import sql
import json

sql("DROP TABLE IF EXISTS usage")
db = get_db()
# print(json.dumps(db.get_print_archive(), indent=4))
for row in db.get_print_archive():
    print('d', (datetime.datetime.fromtimestamp(row[7]) + datetime.timedelta(days=30)).strftime("%Y-%m-%d"))
    for i in range(4):
        if row[10 + 2*i + 1] != 0:
            print('\nr', row[10 + 2*i:10+2*i+2])
            db.update_usage(row[10 + 2*i], row[10 + 2*i + 1], (datetime.datetime.fromtimestamp(row[7]) + datetime.timedelta(days=30)).strftime("%Y-%m-%d"))
    # print(row[10:])
print(db.get_usage())