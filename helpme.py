#!/usr/bin/env python3
import os
import base64
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ---- Config ----
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CLIENT_SECRETS_FILE = "./common/credentials.json"  # Downloaded from Google Cloud Console
TOKEN_FILE = "./common/emailtoken.json"
#
# pick up logs dir from env, defaulting to /data/logs
LOGS_DIR = os.getenv("LOGS_DIR", "/data/logs")
LOG_FILE = os.path.join(LOGS_DIR, "bambu_manager", "latest.log")  # Path to the file you want to attach

TO = "chartier@ucsc.edu"
SUBJECT = "print server error"
BODY = """Hi Cedric,

The server wont run, please fix me

Thanks!
"""

# ---- Get credentials ----
def get_creds():
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.valid:
            return creds
    except Exception:
        pass

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    creds = flow.run_local_server(port=8080, open_browser=False)
    with open(TOKEN_FILE, "w") as token:
        token.write(creds.to_json())
    return creds

# ---- Create MIME message with attachment ----
def create_message_with_attachment(to_addr, subject, body, filename):
    message = MIMEMultipart()
    message["to"] = to_addr
    message["subject"] = subject

    # Text part
    message.attach(MIMEText(body, "plain"))

    # Attachment part
    if os.path.exists(filename):
        with open(filename, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(filename)}"')
        message.attach(part)
    else:
        print(f"⚠️  Log file not found: {filename}")

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw_message}

# ---- Main ----
def main():
    creds = get_creds()
    service = build("gmail", "v1", credentials=creds)

    message = create_message_with_attachment(TO, SUBJECT, BODY, LOG_FILE)
    sent = service.users().messages().send(userId="me", body=message).execute()

    print(f"✅ Email with attachment sent to {TO}. Message ID: {sent.get('id')}")

if __name__ == "__main__":
    main()
