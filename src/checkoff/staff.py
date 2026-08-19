"""Who is allowed to submit a check-off.

The authority is the staff of the Canvas course being graded, cached in
common/staff.txt and refreshed when it goes stale.

The access-control database also tracks staff, but it is synced from whatever
course src/server/canvas.py is pointed at, which is not necessarily the course
these check-offs belong to. Use it with --staff-source db when the two courses
are the same.
"""

import os
import time
from typing import List, Optional

from src import canvas_util, log
from src.checkoff.config import Config

logger = log.setup_logs("checkoff", log.INFO)

CACHE_FILE = "staff.txt"
DEFAULT_ROLES = ["teacher", "ta", "designer"]
DEFAULT_MAX_AGE = 24 * 60 * 60  # refresh the cache once a day


class StaffList:
    """Staff membership lookup, backed by a Canvas snapshot or the access DB."""

    def __init__(self, source: str, members: Optional[List[str]] = None, server=None):
        self.source = source
        self.members = members or []
        self._server = server

    def __contains__(self, cruzid: str) -> bool:
        cruzid = canvas_util.norm(cruzid)
        if not cruzid:
            return False
        if self._server is not None:
            return bool(self._server.is_staff(cruzid=cruzid))
        return cruzid in self.members

    def __len__(self) -> int:
        if self._server is not None:
            return self._count_in_database()
        return len(self.members)

    def _count_in_database(self) -> int:
        try:
            return self._server.sql("SELECT COUNT(*) FROM staff").fetchone()[0]
        except Exception as e:
            logger.warning("Could not count staff in the access database: %s", e)
            return 0

    def describe(self) -> str:
        return f"{self.source} ({len(self)} staff)"


def _from_database() -> Optional[StaffList]:
    """The access-control database, if it is importable on this machine."""
    try:
        from src.server import server
    except Exception as e:
        logger.info("Access database unavailable (%s)", e)
        return None
    return StaffList("access database", server=server)


def _from_canvas(cfg: Config, roles: Optional[List[str]] = None) -> StaffList:
    """Read staff straight from the check-off course's Canvas enrollments."""
    roles = roles or cfg.section("checkoff").get("staff_roles") or DEFAULT_ROLES
    canvas = canvas_util.connect(cfg.api_url, cfg.token)
    course = canvas.get_course(cfg.course_id)

    members = set()
    for user in course.get_users(
        enrollment_type=roles,
        enrollment_state=["active"],
        include=canvas_util.USER_INCLUDES,
    ):
        who = canvas_util.identity_of(user, canvas)
        if who.cruzid:
            members.add(who.cruzid)
        else:
            logger.warning("Staff user %s has no usable CruzID", who)

    ordered = sorted(members)
    write_cache(cfg, ordered)
    return StaffList(f"Canvas course {course.id}", ordered)


def write_cache(cfg: Config, members: List[str]) -> str:
    path = cfg.common_path(CACHE_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(members) + ("\n" if members else ""))
    logger.info("Cached %d staff CruzID(s) to %s", len(members), path)
    return path


def read_cache(cfg: Config) -> Optional[StaffList]:
    path = cfg.common_path(CACHE_FILE)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        members = [line.strip().lower() for line in f if line.strip()]
    if not members:
        return None
    return StaffList(f"cache {path}", members)


def cache_age(cfg: Config) -> Optional[float]:
    path = cfg.common_path(CACHE_FILE)
    if not os.path.exists(path):
        return None
    return time.time() - os.path.getmtime(path)


def load(cfg: Config, prefer: str = "auto") -> StaffList:
    """Return the staff list. `prefer` is one of auto, db, canvas, file."""
    if prefer == "canvas":
        return _from_canvas(cfg)

    if prefer == "file":
        cached = read_cache(cfg)
        if cached is None:
            raise RuntimeError(f"No cached staff list at {cfg.common_path(CACHE_FILE)}")
        return cached

    if prefer == "db":
        from_db = _from_database()
        if from_db is None:
            raise RuntimeError("The access-control database is not available here.")
        if len(from_db) == 0:
            raise RuntimeError(
                "The access-control database has no staff in it. Run the Canvas "
                "sync first, or use --staff-source canvas."
            )
        return from_db

    # auto: the cache for this course, refreshed when missing or stale.
    max_age = cfg.section("checkoff").get("staff_max_age", DEFAULT_MAX_AGE)
    age = cache_age(cfg)
    cached = read_cache(cfg)
    if cached is not None and age is not None and age < max_age:
        return cached
    return _from_canvas(cfg)


def refresh(cfg: Config, roles: Optional[List[str]] = None) -> StaffList:
    """Re-read staff from Canvas and rewrite the cache."""
    return _from_canvas(cfg, roles)
