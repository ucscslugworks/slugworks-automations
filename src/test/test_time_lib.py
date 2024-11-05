import datetime
import time

time_str = "2024-11-04T22:25:23 +0000"
# print(time.daylight)
print(time.mktime(time.strptime("2024-11-04T22:25:23 +0000", "%Y-%m-%dT%H:%M:%S %z")))
print(datetime.datetime.fromisoformat("2024-11-04T22:25:23Z").timestamp())
