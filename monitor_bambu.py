#!/usr/bin/env python3
import os
import time
import base64
import uuid
import tempfile
import subprocess
from typing import Optional

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Config
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]
CLIENT_SECRETS_FILE = os.path.join(".", "common", "credentials.json")
TOKEN_FILE = os.path.join(".", "common", "emailtoken.json")
LOGS_DIR = os.getenv("LOGS_DIR", "/data/logs")
MANAGER_LOG = os.path.join(LOGS_DIR, "bambu_manager", "latest.log")
BAMBU_LOG = os.path.join(LOGS_DIR, "bambu", "latest.log")
ROOT_LOG = os.path.join(LOGS_DIR, "root", "latest.log")
PID_FILE = os.path.join(".", "pid_bambu_printers")
START_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "start_bambu_unsafe")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "chartier@ucsc.edu")
WAIT_MINUTES = int(os.getenv("RESTART_WAIT_MINUTES", "15"))
POLL_INTERVAL = int(os.getenv("RESTART_POLL_SECONDS", "30"))


def get_creds():
    # Try loading existing token and refresh if needed
    creds = None
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    except Exception:
        creds = None

    if creds:
        try:
            if creds.valid:
                return creds
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(TOKEN_FILE, "w") as token:
                    token.write(creds.to_json())
                return creds
        except Exception:
            pass

    # Fall back to interactive auth; bind to an ephemeral or configured port to avoid conflicts
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    port = int(os.getenv("GMAIL_AUTH_PORT", "0"))  # 0 = any free port
    creds = flow.run_local_server(host="127.0.0.1", port=port, open_browser=False)
    with open(TOKEN_FILE, "w") as token:
        token.write(creds.to_json())
    return creds


def is_manager_running() -> bool:
    # Prefer PID check
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
                print(f"checking pid {pid}")
            try:
                os.kill(pid, 0)
                return True
            except Exception:
                print("no such process")
                
    except Exception:
        pass

    # Fallback: log freshness check (5 min)
    for path in (MANAGER_LOG, BAMBU_LOG, ROOT_LOG):
        try:
            if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < 5 * 60:
                print(f"fresh log found: {path}")
                print(time.time() - os.path.getmtime(path))
                return True
        except Exception:
            pass

    return False


def tail_text(path: str, n: int = 200) -> str:
    try:
        with open(path, "rb") as f:
            try:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                block = 8192
                data = b""
                while size > 0 and data.count(b"\n") <= n:
                    step = min(block, size)
                    size -= step
                    f.seek(size)
                    data = f.read(step) + data
                lines = data.splitlines()[-n:]
                return b"\n".join(lines).decode(errors="ignore")
            except Exception:
                f.seek(0)
                return f.read().decode(errors="ignore")
    except Exception:
        return "(unavailable)"


def build_report_attachment(token: str, candidates: list[str]) -> str:
    report = [
        f"Bambu monitor report token [{token}]",
        f"LOGS_DIR={LOGS_DIR}",
        "",
    ]
    for p in candidates:
        report.append(f"===== {p} =====")
        if os.path.exists(p):
            report.append(tail_text(p, 400))
        else:
            report.append("(file not found)")
        report.append("")

    fd, path = tempfile.mkstemp(prefix=f"bambu-monitor-{token}-", suffix=".txt")
    with os.fdopen(fd, "w") as tf:
        tf.write("\n".join(report))
    return path


def build_email(subject: str, body: str, attachments: list[str]) -> dict:
    message = MIMEMultipart()
    message["to"] = ADMIN_EMAIL
    message["subject"] = subject
    message.attach(MIMEText(body, "plain"))

    for filename in attachments:
        if not filename:
            continue
        try:
            if os.path.exists(filename):
                with open(filename, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(filename)}"')
                message.attach(part)
        except Exception:
            # ignore individual attachment failures
            pass

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw_message}


def send_restart_request(service, token: str, subject: str):
    body = (
        "The Bambu manager appears to be stopped.\n\n"
        "Reply with YES to restart, or NO to skip.\n\n"
        f"Token: [{token}]\n"
        f"Tried to attach logs from:\n- {MANAGER_LOG}\n- {BAMBU_LOG}\n- {ROOT_LOG}\n"
    )
    candidates = [MANAGER_LOG, BAMBU_LOG, ROOT_LOG]
    report_path = build_report_attachment(token, candidates)
    attachments = [p for p in candidates if os.path.exists(p)] + [report_path]
    msg = build_email(subject, body, attachments)
    # send initial message (new thread)
    return service.users().messages().send(userId="me", body=msg).execute()


def send_restart_confirmation(service, token: str, success: bool, thread_id: Optional[str] = None, original_subject: Optional[str] = None):
    status = "SUCCESS" if success else "FAILED"
    subject = f"Re: {original_subject}" if original_subject else f"Bambu manager restart {status} [{token}]"
    body = (
        f"Restart status: {status}\n\n"
        f"Logs attached from:\n- {MANAGER_LOG}\n- {BAMBU_LOG}\n- {ROOT_LOG}\n"
    )
    candidates = [MANAGER_LOG, BAMBU_LOG, ROOT_LOG]
    report_path = build_report_attachment(token + "-post", candidates)
    attachments = [p for p in candidates if os.path.exists(p)] + [report_path]
    msg = build_email(subject, body, attachments)
    # if thread_id provided, send as a reply in that thread
    if thread_id:
        msg["threadId"] = thread_id
    return service.users().messages().send(userId="me", body=msg).execute()


def fetch_reply(service, token: str, thread_id: Optional[str] = None) -> Optional[str]:
    if thread_id:
        # Read messages in the same thread to find YES/NO
        thr = service.users().threads().get(userId="me", id=thread_id).execute()
        for m in thr.get("messages", [])[1:]:  # skip the first (our request)
            snippet = (m.get("snippet") or "").lower()
            if "yes" in snippet:
                return "YES"
            if "no" in snippet:
                return "NO"
            payload = m.get("payload", {})
            parts = payload.get("parts") or []
            def walk(parts):
                texts = []
                for p in parts:
                    mime = p.get("mimeType", "")
                    if mime == "text/plain" and p.get("body", {}).get("data"):
                        import base64 as b64
                        texts.append(b64.urlsafe_b64decode(p["body"]["data"]).decode(errors="ignore"))
                    elif p.get("parts"):
                        texts.extend(walk(p.get("parts")))
                return texts
            for text in walk(parts):
                t = text.lower()
                if "yes" in t:
                    return "YES"
                if "no" in t:
                    return "NO"
        return None
    # Fallback: search by subject token
    q = f'subject:"[{token}]" from:{ADMIN_EMAIL} newer_than:2d in:anywhere'
    resp = service.users().messages().list(userId="me", q=q, maxResults=5).execute()
    for item in resp.get("messages", []):
        msg = service.users().messages().get(userId="me", id=item["id"]).execute()
        snippet = (msg.get("snippet") or "").lower()
        if "yes" in snippet:
            return "YES"
        if "no" in snippet:
            return "NO"
        payload = msg.get("payload", {})
        parts = payload.get("parts") or []
        def walk(parts):
            texts = []
            for p in parts:
                mime = p.get("mimeType", "")
                if mime == "text/plain" and p.get("body", {}).get("data"):
                    import base64 as b64
                    texts.append(b64.urlsafe_b64decode(p["body"]["data"]).decode(errors="ignore"))
                elif p.get("parts"):
                    texts.extend(walk(p.get("parts")))
            return texts
        for text in walk(parts):
            t = text.lower()
            if "yes" in t:
                return "YES"
            if "no" in t:
                return "NO"
    return None


def restart_manager() -> bool:
    try:
        env = os.environ.copy()
        if not os.access(START_SCRIPT, os.X_OK):
            os.chmod(START_SCRIPT, 0o755)
        proc = subprocess.run([START_SCRIPT], cwd=os.path.dirname(START_SCRIPT), env=env)
        return proc.returncode == 0
    except Exception:
        return False


def main():
    if is_manager_running():
        print("Manager is running; nothing to do.")
        return 0

    creds = get_creds()
    gmail = build("gmail", "v1", credentials=creds)
    token = uuid.uuid4().hex[:8].upper()

    request_subject = f"Bambu manager down - approve restart? [{token}]"
    sent = send_restart_request(gmail, token, request_subject)
    thread_id = sent.get("threadId")
    print(f"Sent approval request with token [{token}] thread [{thread_id}]")

    deadline = time.time() + WAIT_MINUTES * 60
    while time.time() < deadline:
        resp = fetch_reply(gmail, token, thread_id=thread_id)
        if resp == "YES":
            print("Approval received: YES. Restarting...")
            ok = restart_manager()
            time.sleep(10)
            ok = ok and is_manager_running()
            try:
                send_restart_confirmation(gmail, token, ok, thread_id=thread_id, original_subject=request_subject)
            except Exception:
                pass
            print("Restart result:", "success" if ok else "failed")
            return 0 if ok else 1
        elif resp == "NO":
            print("Approval received: NO. Skipping restart.")
            try:
                send_restart_confirmation(gmail, token, False, thread_id=thread_id, original_subject=request_subject)
            except Exception:
                pass
            return 2
        time.sleep(POLL_INTERVAL)

    print("No approval received; skipping restart.")
    try:
        send_restart_confirmation(gmail, token, False, thread_id=thread_id, original_subject=request_subject)
    except Exception:
        pass
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
