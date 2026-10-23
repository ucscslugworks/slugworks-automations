import time
import traceback

from src import constants, log
from src.bambu_printers import gmail

logger = log.setup_logs(
    "bambu_notifications", additional_handlers=[("bambu", log.INFO)]
)

# from address for all outgoing print notifications
SENDER = '"slugwork Baskin Engineering (BE)" <slugwork@ucsc.edu>'

pending_messages = []

# human-readable reasons a print was canceled - passed to notify_canceled by the manager
REASON_BANNED = "your account is banned from using the Bambu printers"
REASON_INSUFFICIENT_WEIGHT = (
    "you did not have enough filament left in your quarterly limit"
)
REASON_CONCURRENCY = (
    "you already had another print running (only one print at a time is allowed)"
)


def _limit_line(db, cruzid: str):
    # one line describing the user's remaining filament limit, included in every email
    try:
        remaining = db.get_limit(cruzid)
        if remaining == constants.BAMBU_EXEMPT_LIMIT:
            return "You are exempt from the quarterly filament limit."
        return f"You have {round(remaining, 2)}g of filament remaining this quarter."
    except Exception:
        logger.error(f"notifications: {traceback.format_exc()}")
        return "Your remaining filament balance is currently unavailable."


def _send(db, cruzid: str, subject: str, body: str):
    # look up the user's email from their cruzid, append their filament limit, and send
    if not cruzid:
        # prints with no matched form have no cruzid - we don't know who to email
        logger.info("notifications: No cruzid for print, skipping email")
        return

    recipient = f"{cruzid}@ucsc.edu"
    body = f"{body}\n\n{_limit_line(db, cruzid)}\n\nThank you,\nslugwork"

    pending_messages.append(
        {"recipient": recipient, "subject": subject, "body": body, "retry_at": 0}
    )
    send_pending()


def send_pending():
    # keep failed messages for the next loop instead of losing them after archiving
    for message in pending_messages[:]:
        if time.monotonic() < message["retry_at"]:
            continue
        recipient = message["recipient"]
        subject = message["subject"]
        try:
            result = gmail.gmail_send_message(
                recipient, SENDER, subject, message["body"], None, None
            )
            if not result or not result.get("id"):
                raise RuntimeError("Gmail did not return a message ID")
        except Exception:
            message["retry_at"] = time.monotonic() + 60
            logger.error(
                f"notifications: Will retry '{subject}' to {recipient}: {traceback.format_exc()}"
            )
        else:
            pending_messages.remove(message)
            logger.info(f"notifications: Sent '{subject}' to {recipient}")


def notify_canceled(db, cruzid: str, title: str, reason: str):
    # canceled before printing started (ban/limit/concurrency) - nothing was charged
    subject = "Your slugwork print was canceled"
    body = (
        f'Hi {cruzid},\n\nYour print "{title}" was canceled because {reason}.\n\n'
        "No filament was charged for this print."
    )
    _send(db, cruzid, subject, body)


def notify_failed(db, cruzid: str, title: str):
    # failed or canceled after printing started - the weight stays debited
    subject = "Your slugwork print did not finish"
    body = (
        f'Hi {cruzid},\n\nYour print "{title}" did not finish - it failed or was '
        "canceled before completing. The filament for this print still counts "
        "against your quarterly limit.\n\n"
        "If the print failed because of a machine error (not something you did), "
        "take a photo of the failed print and contact the 3D printing management "
        "staff to have the filament restored to your balance."
    )
    _send(db, cruzid, subject, body)


def notify_succeeded(db, cruzid: str, title: str):
    subject = "Your slugwork print is complete"
    body = (
        f'Hi {cruzid},\n\nYour print "{title}" finished successfully.\n\n'
        "Please pick it up from the printer."
    )
    _send(db, cruzid, subject, body)


def notify_recovered(db, cruzid: str, title: str):
    subject = "Please check your slugwork print"
    body = (
        f'Hi {cruzid},\n\nYour print "{title}" is no longer active, but its final '
        "result could not be confirmed.\n\nPlease check the printer or ask staff for help. "
        "Its filament charge has not been changed."
    )
    _send(db, cruzid, subject, body)
