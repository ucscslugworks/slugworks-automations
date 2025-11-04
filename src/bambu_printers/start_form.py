import os
import time
import traceback
import pytz  # added

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src import log

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
START_FORM_SHEET_ID = "1zIMn7G5pq1A7pqQSPIGTQvbvSztVy_QlmRi4wA1HDzA"
SHEET_NAME = "Form Responses 1"
EXPECTED_ROW_LENGTH = 9  # expanded to column I (second 'Printer Used')

START_FORM_OBJECT = None
START_FORM_STARTED = False


def get_start_form():
    global START_FORM_OBJECT, START_FORM_STARTED

    if not START_FORM_STARTED:
        START_FORM_STARTED = True
        START_FORM_OBJECT = StartForm()
        START_FORM_OBJECT.logger.info("get_start_form: Created new StartForm object.")
    else:
        while START_FORM_OBJECT is None:
            time.sleep(1)
        START_FORM_OBJECT.logger.info(
            "get_start_form: Retrieved existing StartForm object."
        )

    return START_FORM_OBJECT


class StartForm:
    def __init__(self):
        self.logger = log.setup_logs(
            "start_form", additional_handlers=[("bambu", log.INFO)]
        )
        common_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "common"
        )

        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists(os.path.join(common_path, "start_form_token.json")):
            creds = Credentials.from_authorized_user_file(
                os.path.join(common_path, "start_form_token.json"), SCOPES
            )
        elif not os.path.exists(os.path.join(common_path, "credentials.json")):
            self.logger.error("init: No credentials.json file found.")
            exit(1)
        # If there are no (valid) credentials available, let the user log in (assuming credentials.json exists).
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    os.path.join(common_path, "credentials.json"), SCOPES
                )
                creds = flow.run_local_server(
                    host="localhost",
                    port=44649,
                    open_browser=False,  # <-- key change
                    authorization_prompt_message="Please open this URL in a browser on your local machine (after SSH port-forward): {url}",
                    success_message="Authentication complete. You may close this tab.",
                )

            # Save the credentials for the next run
            with open(os.path.join(common_path, "start_form_token.json"), "w") as token:
                token.write(creds.to_json())

        try:
            service = build("sheets", "v4", credentials=creds)

            # Call the Sheets API
            self.g_sheets = service.spreadsheets()

        except Exception:
            self.logger.error(f"init: {traceback.format_exc()}")
            exit(1)

        self.latest_row = 1

    def get(self):
        try:
            result = (
                self.g_sheets.values()
                .get(
                    spreadsheetId=START_FORM_SHEET_ID,
                    range=f"{SHEET_NAME}!A{self.latest_row}:I",  # include second printer column
                )
                .execute()
            )

            raw_values = result.get("values", [])
            if not raw_values:
                self.logger.info("get: No data returned.")
                return None

            # Skip header only on very first fetch
            if self.latest_row == 1 and len(raw_values) > 0:
                values = raw_values[1:]
                sheet_row_offset = 2  # data starts at sheet row 2
            else:
                values = raw_values
                sheet_row_offset = self.latest_row

            if not values:
                self.logger.info("get: No new data found.")
                return None

            FORM_TZ = pytz.timezone(os.getenv("FORM_TIMEZONE", "America/Los_Angeles"))

            parsed_rows = []
            for idx, row in enumerate(values):
                # Normalize to EXPECTED_ROW_LENGTH
                row = list(row)
                if len(row) < EXPECTED_ROW_LENGTH:
                    row.extend([""] * (EXPECTED_ROW_LENGTH - len(row)))

                sheet_row_num = sheet_row_offset + idx

                # Column A: Timestamp
                ts_raw = row[0].strip()
                parsed_ts = None
                for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M:%S %p"):
                    try:
                        dt = time.strptime(ts_raw, fmt)
                        # build datetime then localize
                        from datetime import datetime
                        naive = datetime.strptime(ts_raw, fmt)
                        localized = FORM_TZ.localize(naive)
                        parsed_ts = int(localized.astimezone(pytz.UTC).timestamp())
                        break
                    except Exception:
                        continue
                if parsed_ts is None:
                    self.logger.warning(
                        f"get: Skipping row {sheet_row_num} invalid timestamp '{ts_raw}'"
                    )
                    continue

                # Column B: Email -> cruzid
                email_raw = row[1].strip().lower()
                cruzid = email_raw.split("@ucsc.edu")[0] if email_raw else ""

                # Column C: First Printer Used
                printer_primary = row[2].strip()
                # Column I (index 8): Second Printer Used (later in form)
                printer_secondary = row[8].strip()
                printer_final = printer_primary if printer_primary else printer_secondary
                if not printer_final:
                    self.logger.debug(
                        f"get: Row {sheet_row_num} has no printer in C or I; skipping"
                    )
                    continue

                parsed_rows.append([sheet_row_num, parsed_ts, cruzid, printer_final])
                self.logger.debug(
                    f"get: Parsed row {sheet_row_num} -> ts={parsed_ts} cruzid='{cruzid}' printer='{printer_final}'"
                )

            if not parsed_rows:
                self.logger.info("get: No valid new rows after parsing.")
                return None

            self.latest_row = parsed_rows[-1][0] + 1  # next sheet row to start from
            self.logger.info(f"get: Got {len(parsed_rows)} new rows (latest_row now {self.latest_row})")
            return parsed_rows
        except Exception:
            self.logger.error(f"get: {traceback.format_exc()}")
            return None


if __name__ == "__main__":
    sf = StartForm()
    print(sf.get())
