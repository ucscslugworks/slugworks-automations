"""Shared Canvas identity and grading helpers.

Both the access-control sync (src/server/canvas.py) and the walkthrough
check-off tools (src/checkoff/) resolve the same people out of Canvas, so the
matching rules live here and nowhere else.

This module must stay free of import-time side effects: it opens no config,
contacts no API, and touches no database.
"""

from typing import Dict, List, Optional, Tuple

from canvasapi import Canvas

# Fields worth asking for when listing a course roster. Requesting them on the
# paginated roster call avoids a per-user profile fetch.
USER_INCLUDES = ["email", "enrollments", "avatar_url", "login_id", "sis_user_id"]

UCSC_DOMAIN = "ucsc.edu"


def connect(api_url: str, token: str) -> Canvas:
    """Build a Canvas client. Kept here so every caller connects the same way."""
    return Canvas(api_url, token)


def norm(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def looks_like_cruzid(value: Optional[str]) -> bool:
    """True for a plausible CruzID: alphanumeric, and not a bare number.

    UCSC student numbers are all digits, so a numeric value is an SIS student
    ID rather than a CruzID and must never be stored as one.
    """
    text = norm(value)
    return bool(text) and text.isalnum() and not text.isdigit()


class Identity:
    """Every key Canvas gives us for one person, plus the derived CruzID."""

    __slots__ = ("canvas_id", "login_id", "sis_user_id", "email", "name", "cruzid")

    def __init__(
        self,
        canvas_id: str = "",
        login_id: str = "",
        sis_user_id: str = "",
        email: str = "",
        name: str = "",
    ):
        self.canvas_id = canvas_id
        self.login_id = login_id
        self.sis_user_id = sis_user_id
        self.email = email
        self.name = name
        self.cruzid = derive_cruzid(login_id, email, sis_user_id)

    def __repr__(self):
        return (
            f"Identity(canvas_id={self.canvas_id!r}, cruzid={self.cruzid!r}, "
            f"login_id={self.login_id!r}, sis_user_id={self.sis_user_id!r})"
        )


def derive_cruzid(
    login_id: Optional[str] = None,
    email: Optional[str] = None,
    sis_user_id: Optional[str] = None,
) -> str:
    """Work out a CruzID, falling back through the keys Canvas may be missing.

    Order: a ucsc.edu login_id, a bare login_id, a ucsc.edu email, and finally
    sis_user_id -- but only when the SIS value looks like a CruzID rather than
    a student number, so a numeric SIS ID never enters the database as one.
    """
    login = norm(login_id)
    if UCSC_DOMAIN in login:
        return login.split("@")[0]
    if login and "@" not in login and looks_like_cruzid(login):
        return login

    mail = norm(email)
    if UCSC_DOMAIN in mail:
        return mail.split("@")[0]

    sis = norm(sis_user_id)
    if looks_like_cruzid(sis):
        return sis

    return ""


def _get(source, key: str):
    """Read a field from either a dict (a profile) or an object (a User)."""
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def identity_of(source, canvas: Optional[Canvas] = None) -> Identity:
    """Build an Identity from a Canvas User, a submission's user, or a profile.

    Fetches the full user only when the payload is missing both login_id and
    sis_user_id, which submission payloads sometimes are.
    """
    canvas_id = _get(source, "id")
    login = _get(source, "login_id")
    sis = _get(source, "sis_user_id")
    email = _get(source, "email") or _get(source, "primary_email")
    name = _get(source, "short_name") or _get(source, "name")

    if login is None and sis is None and canvas is not None and canvas_id is not None:
        try:
            full = canvas.get_user(canvas_id)
        except Exception:
            full = None
        if full is not None:
            login = login or getattr(full, "login_id", None)
            sis = sis or getattr(full, "sis_user_id", None)
            email = email or getattr(full, "email", None)
            name = (
                name or getattr(full, "short_name", None) or getattr(full, "name", None)
            )

    return Identity(
        canvas_id=str(canvas_id) if canvas_id is not None else "",
        login_id=norm(login),
        sis_user_id=norm(sis),
        email=norm(email),
        name=(name or "").strip(),
    )


def identity_of_submission(sub, canvas: Optional[Canvas] = None) -> Identity:
    """Identity for a submission, using its embedded user when include=['user']."""
    user = getattr(sub, "user", None)
    if user is not None:
        return identity_of(user, canvas)

    user_id = getattr(sub, "user_id", None)
    if user_id is not None and canvas is not None:
        try:
            return identity_of(canvas.get_user(user_id), None)
        except Exception:
            pass
    return Identity(canvas_id=str(user_id) if user_id is not None else "")


# ---------------------------------------------------------------------------
# Cross-course matching
# ---------------------------------------------------------------------------


def build_user_maps(
    course,
    canvas: Canvas,
    enrollment_types: List[str],
    enrollment_states: List[str],
) -> Dict[str, Dict[str, int]]:
    """Three lookup tables for a roster: by Canvas id, login_id, sis_user_id.

    Canvas user IDs hold across course offerings for most people but not all,
    so login_id and sis_user_id back them up.
    """
    by_id: Dict[str, int] = {}
    by_login: Dict[str, int] = {}
    by_sis: Dict[str, int] = {}

    users = course.get_users(
        enrollment_type=enrollment_types,
        enrollment_state=enrollment_states,
        include=USER_INCLUDES,
    )
    for user in users:
        who = identity_of(user, canvas)
        by_id[who.canvas_id] = user.id
        if who.login_id:
            by_login[who.login_id] = user.id
        if who.sis_user_id:
            by_sis[who.sis_user_id] = user.id

    return {"by_id": by_id, "by_login": by_login, "by_sis": by_sis}


def match_user(
    maps: Dict[str, Dict[str, int]], who: Identity
) -> Tuple[Optional[int], str]:
    """Find a person in a target roster. Returns (user id, which key matched)."""
    if who.canvas_id and who.canvas_id in maps["by_id"]:
        return maps["by_id"][who.canvas_id], "id"
    if who.login_id and who.login_id in maps["by_login"]:
        return maps["by_login"][who.login_id], "login_id"
    if who.sis_user_id and who.sis_user_id in maps["by_sis"]:
        return maps["by_sis"][who.sis_user_id], "sis_user_id"
    return None, ""


def find_user_by_cruzid(course, wanted: str):
    """Find an actively enrolled user whose derived CruzID matches exactly."""
    wanted = norm(wanted).split("@")[0]
    if not wanted:
        return None
    for user in course.get_users(search_term=wanted, enrollment_state=["active"]):
        if identity_of(user).cruzid == wanted:
            return user
    return None


# ---------------------------------------------------------------------------
# Assignments and grades
# ---------------------------------------------------------------------------


def resolve_assignment(course, identifier):
    """Look up an assignment by numeric ID or by exact name."""
    text = str(identifier)
    if text.isdigit():
        return course.get_assignment(int(text))
    for assignment in course.get_assignments():
        if assignment.name == identifier:
            return assignment
    raise ValueError(
        f"Assignment '{identifier}' not found in course {course.id} ({course.name})."
    )


def to_float(value) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def is_complete(sub, threshold: float = 1.0) -> bool:
    """True when a submission counts as a completed check-off.

    A numeric score at or above the threshold wins; otherwise a graded
    workflow_state counts, which is how check-offs marked complete without a
    score show up.
    """
    for attr in ("entered_score", "score", "grade"):
        score = to_float(getattr(sub, attr, None))
        if score is not None and score >= threshold:
            return True
    return getattr(sub, "workflow_state", None) == "graded"


def post_grade(assignment, user_id: int, score: float, comment: str = ""):
    """Post a grade, creating and posting the submission even if none exists."""
    sub = assignment.get_submission(user_id)
    sub = sub.edit(submission={"posted_grade": score})
    if comment:
        sub.edit(comment={"text_comment": comment})
    return sub


def module_assignments(course) -> List[Tuple[str, int, int, str]]:
    """Every assignment reachable through a module.

    Returns (module_name, module_id, assignment_id, assignment_title).
    """
    out: List[Tuple[str, int, int, str]] = []
    for module in course.get_modules():
        for item in module.get_module_items():
            if getattr(item, "type", "") == "Assignment":
                out.append((module.name, module.id, item.content_id, item.title))
    return out
