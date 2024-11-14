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

NEVER = -1

UID_LEN = 8

PRINT_EXPIRED = 0
PRINT_SUCCEEDED = 1
PRINT_FAILED = 2
PRINT_CANCELED = 3

NO_FORM_ROW = -1
NO_PRINT_ID = -1
NO_CRUZID = ""

BAMBU_TIMEOUT = (
    10 * 60
)  # max time between form submission & print start (or vice versa)
BAMBU_DEFAULT_LIMIT = 1000  # quarterly weight limit for all users
BAMBU_EXEMPT_LIMIT = float("inf")  # per-print weight limit for exempted users
BAMBU_DELAY = 10  # loop time

BAMBU_FAILED = 0
BAMBU_RUNNING = 1
BAMBU_PAUSE = 2
BAMBU_IDLE = 3
BAMBU_FINISH = 4
BAMBU_UNKNOWN = 5

PRINTER_OFFLINE = 0
PRINTER_IDLE = 1
PRINTER_UNMATCHED = 2
PRINTER_MATCHED = 3

PRINTER_SPOOL_STATES = [
    "Loaded",
    "Loading",
    "Unloading",
    "Unloaded",
    "Error",
]  # last element must be Error for -1 index to work
