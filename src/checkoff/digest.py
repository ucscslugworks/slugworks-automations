"""Weekly summary of everything the check-off scheduler changed.

Sent through the repository's existing Gmail sender
(src/bambu_printers/gmail.py), the same one the print notifications use.
"""

from collections import Counter
from datetime import datetime
from typing import List, Tuple

from src import log
from src.checkoff import grade
from src.checkoff.config import Config

logger = log.setup_logs("checkoff", log.INFO)


def _when(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%a %d %b %H:%M")


def _grade_section(events: List[dict]) -> List[str]:
    runs = [e for e in events if e["job"] == "grade"]
    results = [r for e in runs for r in e.get("results", [])]

    if not results:
        return ["CHECK-OFFS", "  Nothing was checked off this week.", ""]

    counts = Counter(r["status"] for r in results)
    lines = [
        "CHECK-OFFS",
        f"  {len(results)} student(s) processed across "
        f"{sum(e.get('rows', 0) for e in runs)} form submission(s).",
        "",
    ]

    done = [r for r in results if r["status"] == grade.DONE]
    if done:
        lines.append(f"  Newly checked off ({len(done)}):")
        for r in sorted(done, key=lambda r: r["cruzid"]):
            lines.append(f"    {r['cruzid']}  (submitted by {r['submitter']})")
        lines.append("")

    for status, heading in (
        (grade.ALREADY_DONE, "Already done"),
        (grade.STAFF, "Skipped as staff"),
    ):
        if counts.get(status):
            lines.append(f"  {heading}: {counts[status]}")

    problems = [
        r for r in results if r["status"] in (grade.USER_NOT_FOUND, grade.ERROR)
    ]
    if problems:
        lines.append("")
        lines.append(f"  Needs attention ({len(problems)}):")
        for r in problems:
            lines.append(f"    {r['cruzid']}: {r['label']}  (from {r['submitter']})")

    lines.append("")
    return lines


def _transfer_section(events: List[dict]) -> List[str]:
    pairs = [p for e in events if e["job"] == "transfer" for p in e.get("pairs", [])]
    if not pairs:
        return ["GRADE TRANSFERS", "  No transfers ran this week.", ""]

    written = [p for p in pairs if p.get("ok") or p.get("fail")]
    lines = ["GRADE TRANSFERS"]
    if not written:
        lines.append(f"  {len(pairs)} run(s), everything already up to date.")
        lines.append("")
        return lines

    for p in written:
        lines.append(
            f"  {p['source_assignment']} -> {p['target_assignment']}: "
            f"{p['ok']} copied, {p['fail']} failed, {p.get('unchanged', 0)} already correct"
        )
        if p.get("missing"):
            lines.append(
                f"      {p['missing']} source user(s) not found in the target course"
            )
    lines.append("")
    return lines


def _staff_section(events: List[dict]) -> List[str]:
    runs = [e for e in events if e["job"] == "staff"]
    if not runs:
        return ["STAFF LIST", "  No refresh ran this week.", ""]

    added = sorted({c for e in runs for c in e.get("added", [])})
    removed = sorted({c for e in runs for c in e.get("removed", [])})

    lines = [
        "STAFF LIST",
        f"  Refreshed {len(runs)} time(s); {runs[-1].get('count', 0)} staff.",
    ]
    if added:
        lines.append(f"  Added: {', '.join(added)}")
    if removed:
        lines.append(f"  Removed: {', '.join(removed)}")
    if not added and not removed:
        lines.append("  No changes.")
    lines.append("")
    return lines


def _roster_section(events: List[dict]) -> List[str]:
    """The checkout station's ID-card map: stale means cards stop resolving."""
    runs = [e for e in events if e["job"] == "roster"]
    if not runs:
        return ["CHECKOUT ROSTER", "  No refresh ran this week.", ""]

    added = {c for e in runs for c in e.get("added", [])}
    removed = {c for e in runs for c in e.get("removed", [])}

    lines = [
        "CHECKOUT ROSTER",
        f"  Refreshed {len(runs)} time(s); {runs[-1].get('count', 0)} people can swipe in.",
    ]
    # Names, not lists: a course roster churns by the dozen and nobody reads it.
    if added or removed:
        lines.append(f"  {len(added)} added, {len(removed)} removed.")
    else:
        lines.append("  No changes.")
    lines.append("")
    return lines


def _error_section(events: List[dict]) -> List[str]:
    errors = [e for e in events if e["job"] == "error"]
    if not errors:
        return []
    lines = ["ERRORS"]
    for e in errors:
        lines.append(f"  {_when(e['at'])}  {e.get('which', '?')}: {e.get('error', '')}")
    lines.append("")
    return lines


def build(events: List[dict], start: float, end: float) -> Tuple[str, str]:
    """Render the weekly report. Returns (subject, body)."""
    window = f"{datetime.fromtimestamp(start):%a %d %b} - {datetime.fromtimestamp(end):%a %d %b %Y}"

    body = ["Walkthrough check-off report", window, ""]
    body += _grade_section(events)
    body += _transfer_section(events)
    body += _staff_section(events)
    body += _roster_section(events)
    body += _error_section(events)
    body += [
        "This report covers only what the scheduler changed; full detail is in",
        "the checkoff logs on the print server.",
        "",
        "Thank you,",
        "slugwork",
    ]

    checked_off = sum(
        1
        for e in events
        if e["job"] == "grade"
        for r in e.get("results", [])
        if r["status"] == grade.DONE
    )
    subject = f"Walkthrough check-offs: {checked_off} completed this week"

    return subject, "\n".join(body)


def send(cfg: Config, subject: str, body: str) -> bool:
    """Send the report with the repository's existing Gmail sender."""
    recipient = cfg.section("schedule").get("report_recipient")
    if not recipient:
        from src import constants

        recipient = constants.CHECKOFF_REPORT_RECIPIENT

    try:
        # Imported here, not at module scope: gmail runs its OAuth flow on
        # import, which would block the scheduler at startup if the token
        # were missing.
        from src.bambu_printers import gmail, notifications

        result = gmail.gmail_send_message(
            recipient, notifications.SENDER, subject, body, None, None
        )
    except Exception as e:
        logger.error("digest: could not send weekly report: %s", e)
        return False

    if result is None:
        logger.error("digest: weekly report to %s was not sent", recipient)
        return False

    logger.info("digest: sent weekly report to %s", recipient)
    return True
