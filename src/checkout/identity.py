"""Resolve a swiped student ID card to a CruzID via Canvas.

UCSC ID cards carry the student's SIS number. Canvas knows both the SIS number
(`sis_user_id`) and the CruzID (derived from `login_id`/email) for every
enrolled student, so a roster snapshot is a CruzID <-> SIS-ID bridge: swipe the
card, read the SIS number, look up the CruzID, and pre-fill the checkout.

This reuses the repo's Canvas plumbing:
  - src.canvas_util  the shared identity extraction (login_id, sis_user_id ->
                     CruzID) used by both gradecheck and the access sync
  - src.checkoff.config  the same common/canvas.json (auth_token + course_id)
                     the check-off tools read

The roster is cached to common/checkout_roster.json (student CruzID<->SIS data
is sensitive, and common/ is gitignored). Build/refresh it with
`./checkout roster`; the web app only reads the cache, never Canvas directly.
"""

import json
import os
import re
import time

from src import canvas_util, log
from src.checkoff.config import COMMON

logger = log.setup_logs("checkout", log.INFO)

ROSTER_PATH = os.path.join(COMMON, "checkout_roster.json")

# Refresh reminder threshold for the CLI; the web app reads whatever is cached.
DEFAULT_MAX_AGE = 24 * 60 * 60  # one day


def _digits(value):
    return re.sub(r"\D", "", value or "")


# ---- building the roster (Canvas) ---------------------------------------

def build_roster(canvas_cfg, roster_path=ROSTER_PATH):
    """Fetch the course roster from Canvas and cache CruzID<->SIS records.

    `canvas_cfg` is a src.checkoff.config.Config (or anything exposing api_url,
    token, course_id, enrollment_types, enrollment_states). Returns the list of
    student records written.
    """
    canvas = canvas_util.connect(canvas_cfg.api_url, canvas_cfg.token)
    course = canvas.get_course(canvas_cfg.course_id)

    students = []
    seen = set()
    for user in course.get_users(
        enrollment_type=canvas_cfg.enrollment_types,
        enrollment_state=canvas_cfg.enrollment_states,
        include=canvas_util.USER_INCLUDES,
    ):
        who = canvas_util.identity_of(user, canvas)
        if not who.cruzid:
            continue
        if who.cruzid in seen:
            continue
        seen.add(who.cruzid)
        students.append(
            {
                "cruzid": who.cruzid,
                "name": who.name or who.cruzid,
                "sis_user_id": who.sis_user_id,
                "canvas_id": who.canvas_id,
            }
        )

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "generated_ts": time.time(),
        "course_id": canvas_cfg.course_id,
        "count": len(students),
        "students": students,
    }
    os.makedirs(os.path.dirname(roster_path), exist_ok=True)
    tmp = roster_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, roster_path)
    logger.info("Built checkout roster: %d students -> %s", len(students), roster_path)
    return students


def roster_available(roster_path=ROSTER_PATH):
    return os.path.exists(roster_path)


def roster_age(roster_path=ROSTER_PATH):
    """Age of the cached roster in seconds, or None if absent."""
    try:
        return time.time() - os.path.getmtime(roster_path)
    except OSError:
        return None


# ---- resolving a swipe (web app) ----------------------------------------

class Resolver:
    """In-memory lookup from a swiped value to a student, reloaded from the
    roster cache when the file changes."""

    def __init__(self, roster_path=ROSTER_PATH):
        self.roster_path = roster_path
        self._mtime = None
        self._by_cruzid = {}
        self._by_sis = {}
        self._by_sis_digits = {}
        self._by_canvas = {}
        self.generated_at = None
        self.count = 0

    def _reload_if_changed(self):
        try:
            mtime = os.path.getmtime(self.roster_path)
        except OSError:
            # no roster cache yet
            self._mtime = None
            self._by_cruzid = self._by_sis = self._by_sis_digits = self._by_canvas = {}
            self.count = 0
            return
        if mtime == self._mtime:
            return
        with open(self.roster_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        by_cruzid, by_sis, by_sis_digits, by_canvas = {}, {}, {}, {}
        for s in data.get("students", []):
            rec = {"cruzid": s.get("cruzid", ""), "name": s.get("name", "")}
            if s.get("cruzid"):
                by_cruzid[s["cruzid"].lower()] = rec
            sis = str(s.get("sis_user_id") or "")
            if sis:
                by_sis[sis] = rec
                d = _digits(sis).lstrip("0")
                if d:
                    by_sis_digits[d] = rec
            if s.get("canvas_id"):
                by_canvas[str(s["canvas_id"])] = rec
        self._by_cruzid, self._by_sis = by_cruzid, by_sis
        self._by_sis_digits, self._by_canvas = by_sis_digits, by_canvas
        self._mtime = mtime
        self.generated_at = data.get("generated_at")
        self.count = data.get("count", len(data.get("students", [])))

    @property
    def available(self):
        self._reload_if_changed()
        return bool(self._mtime)

    def resolve(self, swipe):
        """Return {"cruzid","name"} for a swiped value, or None.

        Accepts the SIS student number (the card's number, possibly with a
        prefix or leading zeros), a typed CruzID, or a Canvas id.
        """
        self._reload_if_changed()
        if not swipe:
            return None
        value = str(swipe).strip()
        if not value:
            return None

        # Typed CruzID (alphanumeric, not a bare number).
        low = value.lower()
        if low in self._by_cruzid:
            return self._by_cruzid[low]

        # SIS number, exact then digits-only (strip card prefixes / zero pad).
        if value in self._by_sis:
            return self._by_sis[value]
        digits = _digits(value)
        if digits:
            if digits in self._by_sis:
                return self._by_sis[digits]
            stripped = digits.lstrip("0")
            if stripped and stripped in self._by_sis_digits:
                return self._by_sis_digits[stripped]

        # Canvas user id as a last resort.
        if value in self._by_canvas:
            return self._by_canvas[value]
        return None
