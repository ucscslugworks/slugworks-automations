"""Reading common/staff.txt, the cached list of who counts as staff.

src/checkoff/staff.py builds this file from the check-off course's Canvas
teacher/TA/designer enrollments and the scheduler refreshes it daily. Reading
it lives here instead because the readers are scattered -- the checkout app's
admin gate, the Bambu print-limit exemptions -- and most of them have no
business importing Canvas. This module is stdlib-only, so wanting to know who
is staff never drags canvasapi into a process that only prints things.

One file, one answer: nobody is staff when the cache has never been built,
which keeps a missing file from quietly granting anyone anything.
"""

import os
import time

from src.checkoff.config import COMMON

FILENAME = "staff.txt"
PATH = os.path.join(COMMON, FILENAME)


def read(path=PATH):
    """The staff CruzIDs, lowercased. Empty when the cache is missing."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {line.strip().lower() for line in f if line.strip()}
    except OSError:
        return set()


def age(path=PATH):
    """Seconds since the cache was last written, or None if it is not there."""
    try:
        return time.time() - os.path.getmtime(path)
    except OSError:
        return None
