import os
import time
import traceback
import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src import log

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
# defaults to the provided usage sheet
DEFAULT_SHEET_ID = "1XppmTZ--5IxVcsRWJ2nd_ioEjMHJUihbYUDHjAOh9j0"
USAGE_SHEET_ID = os.getenv("USAGE_SHEET_ID", DEFAULT_SHEET_ID)
USAGE_SHEET_NAME = os.getenv("USAGE_SHEET_NAME", "Sheet1")

USAGE_SHEET_OBJECT = None
USAGE_SHEET_STARTED = False


def get_usage_sheet():
    global USAGE_SHEET_OBJECT, USAGE_SHEET_STARTED

    if not USAGE_SHEET_STARTED:
        USAGE_SHEET_STARTED = True
        USAGE_SHEET_OBJECT = UsageSheet()
        USAGE_SHEET_OBJECT.logger.info("get_usage_sheet: Created new UsageSheet object.")
    else:
        while USAGE_SHEET_OBJECT is None:
            time.sleep(1)
        USAGE_SHEET_OBJECT.logger.info("get_usage_sheet: Retrieved existing UsageSheet object.")

    return USAGE_SHEET_OBJECT


class UsageSheet:
    def __init__(self):
        self.logger = log.setup_logs(
            "usage_sheet", additional_handlers=[("bambu", log.INFO)]
        )
        common_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "common"
        )

        creds = None
        token_path = os.path.join(common_path, "status_sheet_token.json")
        creds_path = os.path.join(common_path, "credentials.json")

        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        elif not os.path.exists(creds_path):
            self.logger.error("init: No credentials.json file found.")
            exit(1)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    creds_path,
                    SCOPES,
                )
                creds = flow.run_local_server(
                    host="127.0.0.1",
                    port=int(os.getenv("GOOGLE_OAUTH_PORT", "44650")),
                    open_browser=False,
                    authorization_prompt_message="Open this URL in your local browser (after SSH port-forward): {url}",
                    success_message="Authentication complete. You may close this tab.",
                )

            with open(token_path, "w") as token:
                token.write(creds.to_json())

        try:
            service = build("sheets", "v4", credentials=creds)
            self.g_sheets = service.spreadsheets()
        except Exception:
            self.logger.error(f"init: {traceback.format_exc()}")
            exit(1)

    def update(self, rows):
        """
        Updates the usage sheet with the provided rows (including header).

        Only users with usage this quarter (used_g > 0) are written.
        """
        if not rows or len(rows) < 1:
            self.logger.info("update: No usage rows to write")
            return

        # keep the header row
        header = rows[0]
        data_rows = rows[1:]

        # filter out rows with 0 usage (index 1 is the "used_g" column)
        filtered_rows = [row for row in data_rows if len(row) > 1 and float(row[1]) > 0]

        if not filtered_rows:
            self.logger.info("update: No users with usage this quarter")
            return

        # combine the header with the filtered data
        rows_to_write = [header] + filtered_rows

        try:
            end_col = chr(ord("A") + len(rows_to_write[0]) - 1)
            self.g_sheets.values().update(
                spreadsheetId=USAGE_SHEET_ID,
                range=f"{USAGE_SHEET_NAME}!A1:{end_col}{len(rows_to_write)}",
                valueInputOption="USER_ENTERED",
                body={"values": rows_to_write},
            ).execute()
            self.logger.info(f"update: Wrote {len(filtered_rows)} user rows to usage sheet (quarterly usage only)")
        except Exception:
            self.logger.error(f"update: {traceback.format_exc()}")


if __name__ == "__main__":
    # simple manual run example
    from src.bambu_printers import get_db

    db = get_db()
    sheet = UsageSheet()
    sheet.update([
        ["cruzid", "used_g", "remaining_g", "status", "last_updated"],
        ["example", "0", "1000", "Active", datetime.datetime.now().isoformat()],
    ])
