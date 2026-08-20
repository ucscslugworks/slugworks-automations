"""Resolve a swiped student ID card to a CruzID via Canvas.

UCSC ID cards carry the student's SIS number. Canvas knows both the SIS number
(`sis_user_id`) and the CruzID (derived from `login_id`/email) for every
enrolled student, so a roster snapshot is a CruzID <-> SIS-ID bridge: swipe the
card, read the SIS number, look up the CruzID, and sign that person in.

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

# Rolled into the roster alongside students so staff cards resolve too. Only a
# fallback: canvas.json's checkoff.staff_roles wins when it is set.
STAFF_ROLES = ["teacher", "ta", "designer"]

# A UCSC student number is 7 digits. The card carries more: a two-digit issuing
# number (bumped when a card is reissued) and a trailing digit, none of which
# Canvas knows about. The student number is the leading 7.
SIS_DIGITS = 7


def _digits(value):
    return re.sub(r"\D", "", value or "")


def clean_swipe(value):
    """Strip magstripe framing, leaving the card number or the typed CruzID.

    Readers hand over the whole track the way ISO-7813 writes it, sentinels and
    all: track 2 arrives as ";<number>=<expiry etc>?" and track 1 as
    "%B<number>^SLUG/SAMMY^...?". Only the first field is the card number, and
    none of the punctuation is part of it -- without this a swipe reaches the
    lookups as ";1897343627" and matches nothing.

    A typed CruzID has none of that framing and passes through untouched.
    """
    value = str(value or "").strip()
    if not value:
        return ""
    if value.startswith("%"):
        # The % sentinel is followed by a format-code letter ("B" for a
        # financial card), which is framing rather than part of the number.
        value = value[1:]
        if value[:1].isalpha():
            value = value[1:]
    value = value.lstrip(";")
    # The end sentinel and anything after it (LRC, a reader's newline) is noise.
    value = re.split(r"[?\r\n]", value, maxsplit=1)[0]
    # Field separators: whichever track this is, the number comes first.
    for separator in ("=", "^"):
        if separator in value:
            value = value.split(separator, 1)[0]
    return value.strip()


def _matched(record, via):
    """A copy of a roster record tagged with what the lookup matched on."""
    return dict(record, via=via)


# ---- building the roster (Canvas) ---------------------------------------

def build_roster(canvas_cfg, roster_path=ROSTER_PATH):
    """Fetch the course roster from Canvas and cache CruzID<->SIS records.

    `canvas_cfg` is a src.checkoff.config.Config (or anything exposing api_url,
    token, course_id, enrollment_types, enrollment_states). Returns the list of
    records written.

    Staff roles are pulled in alongside the student enrollments: a TA's card
    has to resolve like anyone else's or they could not sign in at the station
    at all, let alone reach the inventory admin pages.
    """
    canvas = canvas_util.connect(canvas_cfg.api_url, canvas_cfg.token)
    course = canvas.get_course(canvas_cfg.course_id)

    staff_roles = canvas_cfg.section("checkoff").get("staff_roles") or STAFF_ROLES
    roles = list(dict.fromkeys(list(canvas_cfg.enrollment_types) + list(staff_roles)))

    students = []
    seen = set()
    for user in course.get_users(
        enrollment_type=roles,
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
    logger.info("Built checkout roster: %d people -> %s", len(students), roster_path)
    return students


def roster_cruzids(roster_path=ROSTER_PATH):
    """CruzIDs in the cached roster; empty when it has never been built."""
    try:
        with open(roster_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set()
    return {s["cruzid"] for s in data.get("students", []) if s.get("cruzid")}


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
        """Return {"cruzid","name","via"} for a swiped value, or None.

        Accepts the SIS student number (the card's number, possibly with a
        prefix or leading zeros), a typed CruzID, or a Canvas id. "via" says
        which of those matched: sign-in treats a card ("sis") as stronger
        evidence than a CruzID anyone could type ("cruzid").
        """
        self._reload_if_changed()
        value = clean_swipe(swipe)
        if not value:
            return None

        # Typed CruzID (alphanumeric, not a bare number).
        low = value.lower()
        if low in self._by_cruzid:
            return _matched(self._by_cruzid[low], "cruzid")

        # SIS number, exact then digits-only (strip card prefixes / zero pad).
        if value in self._by_sis:
            return _matched(self._by_sis[value], "sis")
        digits = _digits(value)
        if digits:
            if digits in self._by_sis:
                return _matched(self._by_sis[digits], "sis")
            stripped = digits.lstrip("0")
            if stripped and stripped in self._by_sis_digits:
                return _matched(self._by_sis_digits[stripped], "sis")

        # Canvas user id, before any truncation: an exact match on a whole
        # number must always beat a guess made by throwing digits away.
        if value in self._by_canvas:
            return _matched(self._by_canvas[value], "canvas")

        # Last resort, and the usual one for a swipe: drop the issuing number
        # the card carries and the roster does not, and match the student
        # number itself.
        if digits and len(digits) > SIS_DIGITS:
            head = digits[:SIS_DIGITS]
            if head in self._by_sis:
                return _matched(self._by_sis[head], "sis")
            stripped_head = head.lstrip("0")
            if stripped_head and stripped_head in self._by_sis_digits:
                return _matched(self._by_sis_digits[stripped_head], "sis")
        return None
