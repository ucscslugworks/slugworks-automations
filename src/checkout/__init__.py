"""Makerspace item, room-key & consumable checkout web app.

A Home Depot-styled catalog where people check tools and room keys out to
their name (with a due date and a responsibility agreement) and take single-use
supplies. Inventory and the checkout log live in a Google Sheet.

Reuses the repo's shared modules: `src.log` for logging and
`src.checkoff.sheets` for the Google OAuth client + Sheets service.
"""

import os

# src/log.py logs under $LOGS_DIR (default /data/logs, which only exists on the
# deployed Pi). Fall back to a repo-local logs/ dir so the app also runs on a
# dev machine. An explicitly set LOGS_DIR (e.g. /data/logs) still wins.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("LOGS_DIR", os.path.join(_REPO_ROOT, "logs"))
