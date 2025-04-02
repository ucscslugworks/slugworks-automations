import datetime
import os
import time
import traceback

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src import constants, log

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
PRIVATE_SHEET_ID = "1znYsriJMDjESa3nekrVcSBXVW93RLQNJD3YdqRYtN_A"
PRIVATE_SHEET_NAME = "Sheet1"
PUBLIC_SHEET_ID = "1C077MsPnLSphsJT4Q6BA3k3cA0ctSSW_a9yFHQpn2Sk"
PUBLIC_SHEET_NAME = "Sheet1"

STATUS_SHEET_OBJECT = None
STATUS_SHEET_STARTED = False

PRINTER_TEXT = {
    constants.PRINTER_OFFLINE: "Offline",
    constants.PRINTER_IDLE: "Idle",
    constants.PRINTER_UNMATCHED: "Printing, Unmatched",
    constants.PRINTER_MATCHED: "Printing, Matched",
}

GCODE_TEXT = {
    constants.GCODE_IDLE: "Idle",
    constants.GCODE_RUNNING: "Printing",
    constants.GCODE_FINISH: "Finished",
    constants.GCODE_PAUSE: "Paused",
    constants.GCODE_FAILED: "Failed",
    constants.GCODE_UNKNOWN: "Unknown",
}

COLORS = {
    "000000": "Black",
    "0A2989": "Basic Blue",
    "3F8E43": "Basic Green",
    "5E43B7": "Basic Purple",
    "61C680": "Matte Grass Green",
    "68724D": "Matte Dark Green",
    "A3D8E1": "Matte Ice Blue",
    "C12E1F": "Basic Red",
    "E4BD68": "Basic Gold",
    "E8AFCF": "Matte Sakura Pink",
    "F99963": "Matte Mandarin Orange",
    "FFFFFF": "White",
}


def get_status_sheet():
    global STATUS_SHEET_OBJECT, STATUS_SHEET_STARTED

    if not STATUS_SHEET_STARTED:
        STATUS_SHEET_STARTED = True
        STATUS_SHEET_OBJECT = StatusSheet()
        STATUS_SHEET_OBJECT.logger.info(
            "get_status_sheet: Created new StatusSheet object."
        )
    else:
        while STATUS_SHEET_OBJECT is None:
            time.sleep(1)
        STATUS_SHEET_OBJECT.logger.info(
            "get_status_sheet: Retrieved existing StatusSheet object."
        )

    return STATUS_SHEET_OBJECT


class StatusSheet:
    def __init__(self):
        self.logger = log.setup_logs(
            "status_sheet", additional_handlers=[("bambu", log.INFO)]
        )
        common_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "common"
        )

        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists(os.path.join(common_path, "status_sheet_token.json")):
            creds = Credentials.from_authorized_user_file(
                os.path.join(common_path, "status_sheet_token.json"), SCOPES
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
            with open(
                os.path.join(common_path, "status_sheet_token.json"), "w"
            ) as token:
                token.write(creds.to_json())

        try:
            service = build("sheets", "v4", credentials=creds)

            # Call the Sheets API
            self.g_sheets = service.spreadsheets()

        except Exception:
            self.logger.error(f"init: {traceback.format_exc()}")
            exit(1)

        self.latest_row = 1

    def update(self, printer_data: dict):
        """
        Updates the status sheet with the current printer data.

        Args:
            printer_data (dict): The current printer data.

        printer_data is organized as such:
        {
            "printer_name": {
                "status": int from constants.py "PRINTER_" section,
                "last_update": int (epoch time),
                "cruzid": str,
                "gcode_state": int from constants.py "GCODE_" section,
                "percent_complete": percentage (0-100),
                "start_time": int (epoch time),
                "time_remaining": int (seconds),
                "end_time": int (epoch time),
                "weight": int (grams),
                "tool_temp": int (C),
                "tool_temp_target": int (C),
                "bed_temp": int (C),
                "bed_temp_target": int (C),
                "light_state": bool,
                "colors": str - hex codes or text colors as returned by printer,
            },
        }
        """
        try:
            private_table = []
            public_table = []

            for printer, data in printer_data.items():
                private_row = []
                public_row = []

                # printer name
                private_row.append(printer)
                public_row.append(printer)

                # printer status
                private_row.append(PRINTER_TEXT[data["status"]])

                # last update (not public)
                private_row.append(
                    datetime.datetime.fromtimestamp(data["last_update"]).strftime(
                        "%H:%M:%S (%Y-%m-%d)"
                    )
                )

                # cruzid (not public)
                private_row.append(data["cruzid"])

                # print state
                private_row.append(GCODE_TEXT[data["gcode_state"]])

                if data["status"] == constants.PRINTER_OFFLINE:
                    # if offline, show status as offline
                    public_row.append("Offline")
                else:
                    # otherwise, just show print (gcode) status, no need to show printer status (redundant)
                    public_row.append(GCODE_TEXT[data["gcode_state"]])

                if data["gcode_state"] in [
                    constants.GCODE_RUNNING,
                    constants.GCODE_PAUSE,
                ]:
                    # percent progress
                    private_row.append(str(data["percent_complete"]) + "%")
                    public_row.append(str(data["percent_complete"]) + "%")

                    # print start time (not public)
                    private_row.append(
                        datetime.datetime.fromtimestamp(data["start_time"]).strftime(
                            "%H:%M:%S (%Y-%m-%d)"
                        )
                    )

                    # parse time remaining into hours, minutes, seconds
                    time_remaining = data["time_remaining"]
                    hours = 0
                    minutes = 0
                    seconds = 0
                    time_remaining_text = ""

                    if time_remaining >= 60:
                        minutes = time_remaining // 60
                        seconds = time_remaining % 60

                        if minutes > 60:
                            hours = minutes // 60
                            minutes = minutes % 60
                            time_remaining_text += f"{hours}h "

                        time_remaining_text += f"{minutes}m "

                    time_remaining_text += f"{seconds}s"

                    private_row.append(time_remaining_text)
                    public_row.append(time_remaining_text)

                    # print end time
                    private_row.append(
                        datetime.datetime.fromtimestamp(
                            time.time() + time_remaining
                        ).strftime("%H:%M:%S (%Y-%m-%d)")
                    )
                    public_row.append(
                        datetime.datetime.fromtimestamp(
                            time.time() + time_remaining
                        ).strftime("%H:%M:%S (%Y-%m-%d)")
                    )

                    # print weight (not public)
                    private_row.append(f"{data["weight"]}g")
                else:
                    # empty cells
                    private_row += [""] * 5
                    public_row += [""] * 3

                # tool temp (not public)
                private_row.append(
                    f"{data["tool_temp"]}°C / {data["tool_temp_target"]}°C"
                )

                # bed temp (not public)
                private_row.append(
                    f"{data["bed_temp"]}°C / {data["bed_temp_target"]}°C"
                )

                # light state (not public)
                private_row.append("On" if data["light_state"] else "Off")

                # filament colors
                for color in data["colors"].split(","):
                    color_text = "None"
                    if color:  # if string isn't empty
                        color = str(color)
                        if (
                            color.startswith("#") and color[1:7] in COLORS
                        ):  # if known hex code, use color name
                            color_text = COLORS[color[1:7]]
                        else:  # if not a known hex code (or a color string), just use the provided text
                            color_text = color
                    # if string was empty, leave as "None"

                    private_row.append(color_text)
                    public_row.append(color_text)

                # fill in empty colors
                if len(data["colors"].split(",")) < constants.FILAMENT_COUNT:
                    for _ in range(constants.FILAMENT_COUNT - len(data["colors"].split(","))):
                        private_row.append("None")
                        public_row.append("None")
                elif len(data["colors"].split(",")) > constants.FILAMENT_COUNT:
                    private_row = private_row[:-(len(data["colors"].split(",")) - constants.FILAMENT_COUNT)]

                private_table.append(private_row)
                public_table.append(public_row)

            # update private sheet
            self.g_sheets.values().update(
                spreadsheetId=PRIVATE_SHEET_ID,
                range=f"{PRIVATE_SHEET_NAME}!A2:{chr(ord('A') + len(private_table[0]) - 1)}{len(private_table) + 1}",
                valueInputOption="USER_ENTERED",
                body={"values": private_table},
            ).execute()

            # update public sheet
            self.g_sheets.values().update(
                spreadsheetId=PUBLIC_SHEET_ID,
                range=f"{PUBLIC_SHEET_NAME}!A2:{chr(ord('A') + len(public_table[0]) - 1)}{len(public_table) + 1}",
                valueInputOption="USER_ENTERED",
                body={"values": public_table},
            ).execute()

            self.logger.info(f"update: Updated {len(private_table)} rows.")
        except Exception:
            self.logger.error(f"update: {traceback.format_exc()}")


if __name__ == "__main__":
    from src.bambu_printers import get_db

    ss = StatusSheet()
    db = get_db()
    printers = db.get_printer_list()
    data = {}
    for (printer,) in printers:
        data[printer] = db.get_printer_data(printer)
        data[printer]["weight"] = (
            0
            if data[printer]["print_id"] < 0
            else db.get_print_weight(data[printer]["print_id"])
        )
    ss.update(data)
