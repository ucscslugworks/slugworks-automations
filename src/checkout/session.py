"""Who is standing at the checkout station, and what they are allowed to do.

The station is a shared machine, so identity is established once at the start
of a visit -- swipe an ID card or type a CruzID -- and everything after that
(cart, checkout, returns) is attributed to that person without asking again.
The sign-in expires after a short idle period so that the next person to walk
up cannot check things out under the last person's name.

Staff membership comes from common/staff.txt, the same cache the check-off
tools build (src/checkoff/staff.py); refresh it with `./checkout staff`. Only
staff get the inventory admin pages, and that check is made here, on the
server, for every admin request -- hiding the link in the page is decoration,
not access control. A missing cache means nobody is staff, so an unbuilt or
deleted cache locks admin down rather than opening it up.

Neither a swipe nor a typed CruzID is a password, so they are not treated as
equally good: typing a CruzID is enough to check out your own tools, but by
default admin also requires the physical card (the swipe carries the SIS
number, which is not something you can guess from a name). Set
"admin_requires_card": false in checkout.json to drop that second condition.
"""

import os
import stat
import time

from flask import session as flask_session

from src import canvas_util, log, staff_cache
from src.checkoff.config import COMMON

logger = log.setup_logs("checkout", log.INFO)

SECRET_PATH = os.path.join(COMMON, "checkout_session_key")
STAFF_PATH = staff_cache.PATH

# Short on purpose: this is a walk-up kiosk, not a personal login.
DEFAULT_TIMEOUT = 30


def secret_key(path=SECRET_PATH):
    """The key that signs the session cookie, generated once and kept in common/.

    A stable key means a restart does not sign everyone out mid-transaction; a
    per-install random one means cookies from another deployment mean nothing.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            key = f.read().strip()
        if key:
            return key
    except OSError:
        pass
    key = os.urandom(32).hex()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(key + "\n")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    logger.info("Generated a new session key -> %s", path)
    return key


class StaffGate:
    """Staff CruzIDs from the check-off cache, reloaded when the file changes.

    Empty when the cache is missing, which is what makes admin fail closed.
    """

    def __init__(self, staff_path=STAFF_PATH):
        self.staff_path = staff_path
        self._mtime = None
        self._members = set()

    def _reload_if_changed(self):
        try:
            mtime = os.path.getmtime(self.staff_path)
        except OSError:
            # no staff cache yet -> nobody is staff
            self._mtime = None
            self._members = set()
            return
        if mtime == self._mtime:
            return
        self._members = staff_cache.read(self.staff_path)
        self._mtime = mtime

    @property
    def available(self):
        self._reload_if_changed()
        return bool(self._members)

    def __contains__(self, cruzid):
        self._reload_if_changed()
        return canvas_util.norm(cruzid) in self._members

    def __len__(self):
        self._reload_if_changed()
        return len(self._members)


class Gatekeeper:
    """Sign-in, idle expiry, and the staff check, over the Flask session."""

    def __init__(
        self,
        resolver,
        timeout=DEFAULT_TIMEOUT,
        admin_requires_card=True,
        staff_path=STAFF_PATH,
    ):
        self.resolver = resolver
        self.timeout = timeout
        self.admin_requires_card = admin_requires_card
        self.staff = StaffGate(staff_path)

    # ---- signing in / out ------------------------------------------------

    def sign_in(self, swipe, name=None):
        """Start a session from a swiped card or a typed CruzID.

        Returns (user, error): exactly one of the two is set. `user` carries
        `via`, which records whether the card itself was presented.
        """
        value = str(swipe or "").strip()
        if not value:
            return None, "Swipe your ID card or type your CruzID."

        if self.resolver.available:
            match = self.resolver.resolve(value)
            if not match:
                return None, (
                    "Not recognized. Check the CruzID, swipe again, or ask staff "
                    "-- the roster may need a refresh."
                )
            cruzid, person, via = match["cruzid"], match["name"], match["via"]
        else:
            # No roster cache to check against, so take the CruzID at its word
            # and ask for a name. `./checkout roster` turns this branch off.
            cruzid = canvas_util.norm(value)
            if not canvas_util.looks_like_cruzid(cruzid):
                return None, "That doesn't look like a CruzID (try e.g. sslug)."
            person = str(name or "").strip()
            if not person:
                return None, "Enter your name as well."
            via = "typed"

        flask_session.clear()
        flask_session["who"] = {"cruzid": cruzid, "name": person, "via": via}
        self.touch()
        logger.info("Sign-in: %s (%s) via %s", cruzid, person, via)
        return self.current(), None

    def sign_out(self):
        who = flask_session.get("who")
        flask_session.clear()
        if who:
            logger.info("Sign-out: %s", who.get("cruzid"))

    # ---- reading the current session -------------------------------------

    def current(self):
        """The signed-in user, or None once the idle window has passed.

        Staff status is recomputed on every call rather than trusted from the
        cookie, so removing someone from the staff cache takes effect at once.
        """
        who = flask_session.get("who")
        if not who:
            return None
        if self.remaining() <= 0:
            self.sign_out()
            return None
        cruzid = who.get("cruzid", "")
        return {
            "cruzid": cruzid,
            "name": who.get("name", cruzid),
            "via": who.get("via", "typed"),
            "is_staff": self.is_staff(cruzid, who.get("via")),
        }

    def is_staff(self, cruzid, via=None):
        if self.admin_requires_card and via != "sis":
            return False
        return cruzid in self.staff

    def remaining(self):
        """Seconds of inactivity left before the session expires."""
        last = flask_session.get("last_active", 0)
        return max(0, self.timeout - (time.time() - last))

    def touch(self):
        flask_session["last_active"] = time.time()
