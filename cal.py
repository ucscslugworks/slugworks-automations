import datetime
import json
import logging
import os.path
from threading import Thread
from typing import Any, Callable, Iterable, Mapping

import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Change directory to current file location
path = os.path.dirname(os.path.abspath(__file__))
os.chdir(path)

# create new logger with all levels
logger = logging.getLogger("calendar")
logger.setLevel(logging.DEBUG)

# get reader id (0 is the control pi, any other number is a reader pi zero)
try:
    reader_file = json.load(open("ID.json"))
except FileNotFoundError:
    logger.error("No ID.json file found.")
    exit(1)
reader_id = reader_file["id"]

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly", "https://www.googleapis.com/auth/spreadsheets"]

# The ID of the Google Calendar
CALENDAR_ID = "c_a8a4e066260993fdee2b6bd4fcc59fbe28b55377eb82bc6e037d809597e6f745@group.calendar.google.com"

creds = None
# The file token.json stores the user's access and refresh tokens, and is
# created automatically when the authorization flow completes for the first
# time.
if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
elif not os.path.exists("credentials.json"):
    logger.error("No credentials.json file found.")
    exit(1)
# If there are no (valid) credentials available, let the user log in (assuming credentials.json exists).
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=44649)
    # Save the credentials for the next run
    with open("token.json", "w") as token:
        token.write(creds.to_json())

try:
    service = build("calendar", "v3", credentials=creds)

    # Call the Calendar API
    g_calendar = service.events()

except HttpError as e:
    logger.error(e)
    exit(1)


def get_calendar_events(time_min, time_max):
    """
    Get events from the Google Calendar within a specified time range.

    time_min: str: The minimum time to get events from (RFC3339 timestamp).
    time_max: str: The maximum time to get events until (RFC3339 timestamp).

    Returns a DataFrame containing the events.
    """
    try:
        events_result = g_calendar.list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])

        if not events:
            logger.info("No upcoming events found.")
            return pd.DataFrame()

        event_list = []
        for event in events:
            event_list.append({
                "id": event.get("id"),
                "summary": event.get("summary"),
                "description": event.get("description"),
                "start": event.get("start").get("dateTime"),
                "end": event.get("end").get("dateTime"),
            })

        return pd.DataFrame(event_list)

    except HttpError as e:
        logger.error(e)
        return pd.DataFrame()


def get_upcoming_events(days=7):
    """
    Get upcoming events for the next specified number of days.

    days: int: The number of days to get events for.

    Returns a DataFrame containing the events.
    """
    now = datetime.datetime.utcnow().isoformat() + "Z"
    time_max = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).isoformat() + "Z"
    return get_calendar_events(now, time_max)


def main():
    # Create a new directory for logs if it doesn't exist
    if not os.path.exists(path + "/logs/calendar"):
        os.makedirs(path + "/logs/calendar")

    # create new logger with all levels
    root_logger = logging.getLogger("root")
    root_logger.setLevel(logging.DEBUG)

    # create file handler which logs debug messages (and above - everything)
    fh = logging.FileHandler(f"logs/calendar/{str(datetime.datetime.now())}.log")
    fh.setLevel(logging.DEBUG)

    # create console handler which only logs warnings (and above)
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)

    # create formatter and add it to the handlers
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s: %(message)s")
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # add the handlers to the logger
    root_logger.addHandler(fh)
    root_logger.addHandler(ch)

    events_df = get_upcoming_events(7)
    print(events_df)


if __name__ == "__main__":
    main()
