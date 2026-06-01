import traceback

from src import constants, log
from src.bambu_printers import gmail

logger = log.setup_logs(
    "bambu_notifications", additional_handlers=[("bambu", log.INFO)]
)

# from address for all outgoing print notifications
SENDER = "slugwork Baskin Engineering (BE) <slugwork@ucsc.edu>"

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
    remaining = db.get_limit(cruzid)
    if remaining == constants.BAMBU_EXEMPT_LIMIT:
        return "You are exempt from the quarterly filament limit."
    return f"You have {round(remaining, 2)}g of filament remaining this quarter."


def _send(db, cruzid: str, subject: str, body: str):
    # look up the user's email from their cruzid, append their filament limit, and send
    if not cruzid:
        # prints with no matched form have no cruzid - we don't know who to email
        logger.info("notifications: No cruzid for print, skipping email")
        return

    recipient = f"{cruzid}@ucsc.edu"
    body = f"{body}\n\n{_limit_line(db, cruzid)}\n\nThank you,\nslugwork"

    try:
        gmail.gmail_send_message(recipient, SENDER, subject, body, None, None)
        logger.info(f"notifications: Sent '{subject}' to {recipient}")
    except Exception:
        logger.error(f"notifications: {traceback.format_exc()}")


def notify_canceled(db, cruzid: str, title: str, reason: str):
    # canceled before printing started (ban/limit/concurrency) - nothing was charged
    subject = "Your slugwork print was canceled"
    body = (
        f'Hi {cruzid},\n\nYour print "{title}" was canceled because {reason}. '
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
        f'Hi {cruzid},\n\nYour print "{title}" finished successfully. '
        "Please pick it up from the printer."
    )
    _send(db, cruzid, subject, body)
