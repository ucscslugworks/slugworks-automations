"""Who is allowed to submit a check-off.

The access-control database already tracks staff (src/server/canvas.py syncs it
from Canvas enrollments), so that is the authority.  When the database is not
reachable -- running the tools off the check-off machine, say -- this falls back
to Canvas directly and caches the result in common/staff.txt.
"""

import os
from typing import List, Optional

from src import canvas_util, log
from src.checkoff.config import Config

logger = log.setup_logs("checkoff", log.INFO)

CACHE_FILE = "staff.txt"
DEFAULT_ROLES = ["teacher", "ta", "designer"]


class StaffList:
    """Staff membership lookup, backed by the access DB or a Canvas snapshot."""

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
        return len(self.members)


def _from_database() -> Optional[StaffList]:
    """Use the access-control database if it is importable on this machine."""
    try:
        from src.server import server
    except Exception as e:
        logger.info("Access database unavailable (%s); falling back to Canvas", e)
        return None
    return StaffList("access database", server=server)


def _from_canvas(cfg: Config, roles: Optional[List[str]] = None) -> StaffList:
    """Read staff straight from Canvas enrollments and cache them."""
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
    return StaffList("Canvas", ordered)


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
    return StaffList(f"cache ({path})", members)


def load(cfg: Config, prefer: str = "auto") -> StaffList:
    """Return the staff list. `prefer` is one of auto, db, canvas, file."""
    if prefer in ("auto", "db"):
        from_db = _from_database()
        if from_db is not None:
            return from_db
        if prefer == "db":
            raise RuntimeError("The access-control database is not available here.")

    if prefer in ("auto", "file"):
        cached = read_cache(cfg)
        if cached is not None:
            return cached
        if prefer == "file":
            raise RuntimeError(f"No cached staff list at {cfg.common_path(CACHE_FILE)}")

    return _from_canvas(cfg)


def refresh(cfg: Config, roles: Optional[List[str]] = None) -> StaffList:
    """Re-read staff from Canvas and rewrite the cache."""
    return _from_canvas(cfg, roles)
