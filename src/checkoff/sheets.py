"""Google Sheets access for the staff check-off form responses.

Credentials live in common/ with the rest of the repository's Google secrets:

    common/credentials.json   the OAuth client every Google module here shares
    common/token.json         cached user token for the spreadsheets scope

src/sheet.py already holds that token at the same scope, so nothing extra needs
authorizing. Both paths can be overridden with "sheet.credentials_file" and
"sheet.token_file" if this ever needs its own.
"""

import os
import sys
from typing import List, Optional

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

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


class NeedsAuthorization(Exception):
    """Raised when authorizing would need a person and none is available."""


def get_service(cfg: Config, allow_auth: Optional[bool] = None):
    """Return an authorized Sheets service, running the OAuth flow if needed.

    The flow is headless-friendly: it binds a fixed port and prints the URL
    before blocking, so a machine reached over SSH can be authorized from a
    laptop with the port forwarded.

    `allow_auth` defaults to whether stdin is a terminal. That matters for the
    scheduler: run_local_server() blocks until someone completes a browser
    round trip, so a background process must fail loudly instead of hanging
    forever on a token that cannot be refreshed.
    """
    if allow_auth is None:
        allow_auth = sys.stdin.isatty()

    options = cfg.section("sheet")
    credentials_path = cfg.common_path(
        options.get("credentials_file", CREDENTIALS_FILE)
    )
    token_path = cfg.common_path(options.get("token_file", TOKEN_FILE))

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except Exception as e:
                # Revoked or expired beyond refresh - fall through to re-auth.
                logger.warning("Could not refresh %s: %s", token_path, e)
                creds = None

        if not refreshed:
            if not allow_auth:
                raise NeedsAuthorization(
                    f"{token_path} is missing or no longer valid, and this is "
                    "not an interactive session. Run `./checkoff grade` from a "
                    "terminal once to authorize, then let the scheduler resume."
                )
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"{credentials_path} not found. This is the shared Google "
                    "OAuth client; the other Google modules here use it too."
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
