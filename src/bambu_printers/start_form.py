import os
import time
import traceback

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src import log

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
START_FORM_SHEET_ID = "1zIMn7G5pq1A7pqQSPIGTQvbvSztVy_QlmRi4wA1HDzA"
SHEET_NAME = "Form Responses 1"
EXPECTED_ROW_LENGTH = 3

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
        if os.path.exists(os.path.join(common_path, "token.json")):
            creds = Credentials.from_authorized_user_file(
                os.path.join(common_path, "token.json"), SCOPES
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
                creds = flow.run_local_server(port=44649)
            # Save the credentials for the next run
            with open(os.path.join(common_path, "token.json"), "w") as token:
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
                    range=f"{SHEET_NAME}!A{self.latest_row}:C",
                )
                .execute()
            )

            values = result.get("values", [])[1:]

            if not values:
                self.logger.info("get: No new data found.")
                return None

            for i in range(len(values)):
                values[i] = list(values[i][0:EXPECTED_ROW_LENGTH])
                values[i].extend([""] * (EXPECTED_ROW_LENGTH - len(values[i])))

                values[i][0] = time.mktime(
                    time.strptime(str(values[i][0]), "%m/%d/%Y %H:%M:%S")
                )

                if len(values[i][1]) > 0:
                    values[i][1] = str(values[i][1]).lower().split("@ucsc.edu")[0]

                values[i][2] = str(values[i][2]).split(" ")

                if len(values[i][2]) < 1:
                    self.logger.error(f"get: Invalid data in row {self.latest_row + i}")
                    continue

                values[i][2] = values[i][2][0]

                values[i].insert(0, self.latest_row + i)

            self.latest_row += len(values)
            self.logger.info(f"get: Got {len(values)} new rows.")
            return values
        except Exception:
            self.logger.error(f"get: {traceback.format_exc()}")
            return None


if __name__ == "__main__":
    sf = StartForm()
    print(sf.get())
