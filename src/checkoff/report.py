"""Export a CSV of who completed which check-off, and when."""

import csv
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from src import canvas_util, log
from src.checkoff.config import Config

logger = log.setup_logs("checkoff", log.INFO)

COLUMNS = [
    "module",
    "assignment",
    "cruzid",
    "name",
    "email",
    "sis_user_id",
    "completed_at",
    "score",
]

# Modules whose assignments count as check-offs when scanning by module name.
DEFAULT_MODULE_TERMS = [
    "safety walkthrough",
    "club hub",
    "creatorspace",
    "shop",
    "laser cutting",
    "soldering",
    "sewing",
    "3d printer",
    "printer cutter",
]


def parse_ts(value: Optional[str]) -> Optional[datetime]:
    """Parse a Canvas ISO8601 timestamp ('2025-10-01T23:45:12Z')."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def in_range(dt: Optional[datetime], start: datetime, end: datetime) -> bool:
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return start <= dt <= end


def _assignments_from_modules(
    course, terms: List[str]
) -> Dict[int, Tuple[str, Set[str]]]:
    """Assignments belonging to modules whose name contains one of `terms`."""
    found: Dict[int, Tuple[str, Set[str]]] = {}
    for mod_name, _mod_id, aid, title in canvas_util.module_assignments(course):
        lowered = (mod_name or "").strip().lower()
        if not any(term in lowered for term in terms):
            continue
        if aid in found:
            found[aid][1].add(mod_name)
        else:
            found[aid] = (title, {mod_name})
    return found


def gather(
    cfg: Config,
    course_id: int,
    start_date: str,
    end_date: str,
    assignment_ids: Optional[List[int]] = None,
    module_terms: Optional[List[str]] = None,
) -> List[dict]:
    """Completion rows for a course inside a date window.

    Scans an explicit assignment list when given, otherwise every assignment in
    a module whose name matches `module_terms`.
    """
    canvas = canvas_util.connect(cfg.api_url, cfg.token)
    course = canvas.get_course(course_id)
    print(f"[{course.id}] Connected to {cfg.api_url}")

    start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
    print(f"[{course.id}] Window: {start_date} -> {end_date} (UTC inclusive)")

    if assignment_ids:
        targets = {aid: (None, set()) for aid in assignment_ids}
        print(f"[{course.id}] Using {len(targets)} explicit assignment id(s).")
    else:
        terms = module_terms or DEFAULT_MODULE_TERMS
        targets = _assignments_from_modules(course, terms)
        print(f"[{course.id}] Matched {len(targets)} assignment(s) from modules.")
        if not targets:
            return []

    rows: List[dict] = []
    for aid, (title, modules) in targets.items():
        try:
            assignment = course.get_assignment(aid)
        except Exception as e:
            print(f"[{course.id}] Skipping assignment {aid}: {e}")
            logger.warning("Skipping assignment %s in course %s: %s", aid, course.id, e)
            continue
        name = title or assignment.name

        kept = 0
        for sub in assignment.get_submissions(include=["user"], per_page=100):
            # Any score above zero counts here, unlike the 1-point check-off rule.
            if not canvas_util.is_complete(sub, threshold=1e-6):
                continue
            ts = (
                parse_ts(getattr(sub, "graded_at", None))
                or parse_ts(getattr(sub, "submitted_at", None))
                or parse_ts(getattr(sub, "updated_at", None))
            )
            if not in_range(ts, start, end):
                continue

            who = canvas_util.identity_of_submission(sub, canvas)
            rows.append(
                {
                    "module": "; ".join(sorted(modules)),
                    "assignment": name,
                    "cruzid": who.cruzid,
                    "name": who.name,
                    "email": who.email,
                    "sis_user_id": who.sis_user_id,
                    "completed_at": (
                        ts.astimezone(timezone.utc).isoformat() if ts else ""
                    ),
                    "score": getattr(sub, "score", None),
                }
            )
            kept += 1
        print(f"[{course.id}] {name} ({aid}): {kept} row(s) in range")

    rows.sort(
        key=lambda r: (
            r["module"].lower(),
            r["assignment"].lower(),
            r["completed_at"],
            r["cruzid"],
        )
    )
    print(f"[{course.id}] Collected {len(rows)} completion rows.")
    return rows


def write_csv(rows: List[dict], path: str) -> str:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in COLUMNS})
    print(f"Wrote {len(rows)} rows to {path}")
    logger.info("Wrote %d completion rows to %s", len(rows), path)
    return path


def default_path(cfg: Config, course_id: int, start: str, end: str) -> str:
    return os.path.join(
        cfg.log_dir, f"module_completions_{course_id}_{start}_to_{end}.csv"
    )
