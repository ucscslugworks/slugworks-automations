"""Google Sheets access for the staff check-off form responses.

Credentials live in common/ with the rest of the repository's secrets:
    common/checkoff_credentials.json   OAuth client downloaded from Google
    common/checkoff_token.json         cached user token, written on first run
"""

import os
from typing import List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src import log
from src.checkoff.config import Config

logger = log.setup_logs("checkoff", log.INFO)

# Delete the token file after changing these.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

AUTH_PORT = 8080

CREDENTIALS_FILE = "checkoff_credentials.json"
TOKEN_FILE = "checkoff_token.json"


def get_service(cfg: Config):
    """Return an authorized Sheets service, running the OAuth flow if needed.

    The flow is headless-friendly: it binds a fixed port and prints the URL
    before blocking, so a machine reached over SSH can be authorized from a
    laptop with the port forwarded.
    """
    credentials_path = cfg.common_path(CREDENTIALS_FILE)
    token_path = cfg.common_path(TOKEN_FILE)

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"{credentials_path} not found. Download the OAuth client "
                    "credentials from the Google Cloud console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            print(
                f"Open http://localhost:{AUTH_PORT} on your local machine to authorize."
            )
            logger.info("Waiting for Google OAuth on port %s", AUTH_PORT)
            creds = flow.run_local_server(port=AUTH_PORT, open_browser=False)
        with open(token_path, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
        logger.info("Saved Google credentials to %s", token_path)

    return build("sheets", "v4", credentials=creds)


def read_range(
    service, spreadsheet_id: str, cell_range: str, width: int
) -> List[List[str]]:
    """Read a range, padding every row out to `width` columns."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=cell_range)
        .execute()
    )
    rows = result.get("values", [])
    return [row + [""] * max(0, width - len(row)) for row in rows]


def write_range(service, spreadsheet_id: str, cell_range: str, values: List[List[str]]):
    return (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=cell_range,
            valueInputOption="USER_ENTERED",
            body={"values": values},
        )
        .execute()
    )
