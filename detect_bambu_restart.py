import os
import sys
import time

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    try:
        if (
            os.path.getmtime(os.path.join("logs", "bambu", "latest.log"))
            < time.time() - 60 * 5
        ):
            sys.exit(1)
    except Exception:
        sys.exit(1)

    sys.exit(0)
