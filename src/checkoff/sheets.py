"""Google Sheets access for the staff check-off form responses.

Authorization is a copy-paste flow, because the print server has no browser and
Google removed the out-of-band flow in 2022. You open the URL on whatever
machine does have a browser; Google redirects to http://localhost:8080/ there,
which fails to connect but puts the code in the address bar; you paste that URL
back. Nothing needs to reach the server's own localhost.

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
from urllib.parse import parse_qs, urlparse

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

# Must be one of the OAuth client's authorized redirect URIs. The browser is
# never expected to actually reach it.
REDIRECT_URI = f"http://localhost:{AUTH_PORT}/"

PASTE_PROMPT = """
Authorize this on any machine with a browser:

  1. Open this URL:

{url}

  2. Sign in and approve. The browser will then fail to load a
     "localhost" page - that is expected, nothing is listening there.

  3. Copy the whole address it tried to load and paste it below.
     It looks like: {redirect}?state=...&code=4/0A...&scope=...
"""


def extract_code(response: str) -> str:
    """Pull the authorization code out of a pasted redirect URL, or take it raw."""
    response = response.strip()
    if not response:
        raise ValueError("Nothing pasted.")

    if "code=" in response:
        query = urlparse(response).query or response.split("?", 1)[-1]
        codes = parse_qs(query).get("code")
        if not codes:
            raise ValueError("That URL has no 'code' parameter.")
        return codes[0]

    if "://" in response:
        raise ValueError("That URL has no 'code' parameter.")

    # Assume the user pasted just the code itself.
    return response


def authorize(cfg: Config, use_local_server: bool = False):
    """Run the OAuth flow and save the token. Returns the credentials."""
    options = cfg.section("sheet")
    credentials_path = cfg.common_path(
        options.get("credentials_file", CREDENTIALS_FILE)
    )
    token_path = cfg.common_path(options.get("token_file", TOKEN_FILE))

    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            f"{credentials_path} not found. This is the shared Google OAuth "
            "client; the other Google modules here use it too."
        )

    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)

    if use_local_server:
        print(f"Open http://localhost:{AUTH_PORT} on this machine to authorize.")
        logger.info("Waiting for Google OAuth on port %s", AUTH_PORT)
        creds = flow.run_local_server(port=AUTH_PORT, open_browser=False)
    else:
        flow.redirect_uri = REDIRECT_URI
        # prompt="consent" so Google always returns a refresh token; without it
        # a re-authorization can come back access-token-only and expire in an
        # hour, which is how the previous token ended up unusable.
        url, _state = flow.authorization_url(access_type="offline", prompt="consent")
        print(PASTE_PROMPT.format(url=url, redirect=REDIRECT_URI))

        code = extract_code(input("Paste the URL (or just the code) here: "))
        flow.fetch_token(code=code)
        creds = flow.credentials

    with open(token_path, "w", encoding="utf-8") as token:
        token.write(creds.to_json())
    print(f"Authorized. Token saved to {token_path}")
    logger.info("Saved Google credentials to %s", token_path)

    if not getattr(creds, "refresh_token", None):
        print(
            "Warning: Google did not return a refresh token, so this will stop "
            "working within the hour. Re-run `./checkoff auth` to try again."
        )
        logger.warning("Google returned no refresh token for %s", token_path)

    return creds


CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


class NeedsAuthorization(Exception):
    """Raised when authorizing would need a person and none is available."""


def get_service(cfg: Config, allow_auth: Optional[bool] = None):
    """Return an authorized Sheets service, authorizing if the token is dead.

    `allow_auth` defaults to whether stdin is a terminal. That matters for the
    scheduler: authorizing waits for a person to paste a code, so a background
    process must fail loudly instead of hanging forever on a token that cannot
    be refreshed.
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
                    "not an interactive session. Run `./checkoff auth` from a "
                    "terminal once, then let the scheduler resume."
                )
            creds = authorize(cfg)
        else:
            with open(token_path, "w", encoding="utf-8") as token:
                token.write(creds.to_json())
            logger.info("Refreshed Google credentials in %s", token_path)

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
