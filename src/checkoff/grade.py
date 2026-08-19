"""Check students off from the staff Google Form responses.

Staff submit a form with the CruzIDs they just walked through; the response
sheet is both the work queue and the audit log.  Rows whose status column is
still empty get processed, then the status is written back so the next run
skips them.
"""

from typing import List, Tuple

from canvasapi.exceptions import CanvasException

from src import canvas_util, log
from src.checkoff import sheets
from src.checkoff import staff as staff_module
from src.checkoff.config import Config

logger = log.setup_logs("checkoff", log.INFO)

# Status codes. The strings land in the sheet where staff read them directly,
# so keep the wording stable.
ERROR = -2
USER_NOT_FOUND = -1
DONE = 0
ALREADY_DONE = 1
STAFF = 2
WOULD_CHECK_OFF = 3

STATUS_STRINGS = {
    ERROR: "Error",
    USER_NOT_FOUND: "User not found",
    DONE: "Done",
    ALREADY_DONE: "Already done",
    STAFF: "Staff",
    WOULD_CHECK_OFF: "Would check off (dry run)",
}

NOT_STAFF = "Submitter is not staff"
NO_IDS = "No CruzIDs given"

SHEET_WIDTH = 4  # timestamp, submitter email, CruzIDs, status


def split_cruzids(cell: str) -> List[str]:
    """Split the free-text CruzID cell staff type into individual IDs."""
    text = str(cell).replace("\n", ",").replace(";", ",").replace(" ", ",")
    return [
        canvas_util.norm(part).split("@")[0] for part in text.split(",") if part.strip()
    ]


def check_off_one(
    course, assignment, who: str, staff, dry_run: bool
) -> Tuple[int, str]:
    """Grade one student. Returns (status code, detail for the log)."""
    if who in staff:
        return STAFF, ""

    try:
        user = canvas_util.find_user_by_cruzid(course, who)
        if user is None:
            return USER_NOT_FOUND, ""

        sub = assignment.get_submission(user.id)
        if canvas_util.is_complete(sub):
            return ALREADY_DONE, ""
        if dry_run:
            return WOULD_CHECK_OFF, ""

        sub = sub.edit(submission={"posted_grade": 1})
        if canvas_util.is_complete(sub):
            return DONE, ""
        return ERROR, "grade did not stick"
    except CanvasException as e:
        return ERROR, str(e)
    except Exception as e:
        # One bad row must not stop the run.
        return ERROR, f"{type(e).__name__}: {e}"


def run(cfg: Config, dry_run: bool = False, staff_source: str = "auto") -> dict:
    """Process every unhandled row.

    Returns {"rows": int, "results": [...]} where each result records one
    student's outcome, which the weekly digest summarises.
    """
    spreadsheet_id = cfg.require("sheet", "spreadsheet_id")
    cell_range = cfg.section("sheet").get("range", "Form Responses 1!A2:D")
    assignment_id = cfg.require("checkoff", "assignment_id")

    canvas = canvas_util.connect(cfg.api_url, cfg.token)
    course = canvas.get_course(cfg.course_id)
    assignment = canvas_util.resolve_assignment(course, assignment_id)

    staff = staff_module.load(cfg, prefer=staff_source)
    logger.info("Staff list from %s", staff.describe())
    print(f"Staff list: {staff.describe()}")

    service = sheets.get_service(cfg)
    values = sheets.read_range(service, spreadsheet_id, cell_range, SHEET_WIDTH)
    summary = {"rows": 0, "results": []}
    if not values:
        print("No form responses found.")
        return summary

    changed = 0
    for row in values:
        if row[3].strip():  # already handled on an earlier run
            continue

        submitter = canvas_util.norm(row[1]).split("@")[0]
        if submitter not in staff:
            row[3] = NOT_STAFF
            logger.warning(
                "Rejected check-off from %s: not in %s",
                submitter,
                staff.describe(),
            )
            changed += 1
            continue

        ids = split_cruzids(row[2])
        if not ids:
            row[3] = NO_IDS
            changed += 1
            continue

        notes = []
        for who in ids:
            status, detail = check_off_one(course, assignment, who, staff, dry_run)
            label = STATUS_STRINGS[status] + (f" ({detail})" if detail else "")
            print(f"  {who}: {label}")
            logger.info("%s -> %s (by %s)", who, label, submitter)
            notes.append(f"{who}: {label}")
            summary["results"].append(
                {
                    "cruzid": who,
                    "status": status,
                    "label": label,
                    "submitter": submitter,
                }
            )
        row[3] = "\n".join(notes)
        changed += 1

    summary["rows"] = changed

    if not changed:
        print("Nothing new to check off.")
        return summary

    if dry_run:
        print(f"Dry run: {changed} row(s) would be updated; sheet left untouched.")
        return summary

    sheets.write_range(service, spreadsheet_id, cell_range, values)
    print(f"Updated {changed} row(s) in the response sheet.")
    logger.info("Updated %d row(s) in the response sheet", changed)
    return summary
