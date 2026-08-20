"""Flask web app for the makerspace checkout system.

Home Depot-styled catalog + cart. Instead of buying, you check items and room
keys out to your name with a due date, and take single-use supplies. Data lives
in a Google Sheet (see store.py / bootstrap.py).

You sign in once when you walk up -- swipe your ID or type your CruzID -- and
the station remembers you until you go idle (see session.py), so nothing after
that asks who you are. Every request is checked against that session here on
the server: the API refuses to act for a signed-out browser, the inventory
admin pages refuse anyone who is not staff, and a student can only return their
own checkouts.
"""

import os

from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

from src import log
from src.checkout import config as config_module
from src.checkout import identity
from src.checkout import session as session_module
from src.checkout.store import SheetStore

logger = log.setup_logs("checkout", log.INFO)

# Reachable without a session: the shell of the front page and the sign-in API
# it posts to. Everything else -- including anything added later -- is gated.
PUBLIC_ENDPOINTS = {"static", "index", "api_session", "api_login", "api_logout"}


def create_app(cfg=None):
    cfg = cfg or config_module.load()
    store = SheetStore(cfg, allow_auth=False)
    # Resolves swiped ID cards -> CruzID from the cached Canvas roster
    # (built by `./checkout roster`). Reloads itself when that cache changes.
    resolver = identity.Resolver()
    # Who is at the station right now, and whether they are staff (from the
    # common/staff.txt cache, built by `./checkout staff`).
    gate = session_module.Gatekeeper(
        resolver,
        timeout=cfg.session_timeout_seconds,
        admin_requires_card=cfg.admin_requires_card,
    )

    app = Flask(__name__)  # templates/ and static/ are alongside this module
    app.secret_key = session_module.secret_key()
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

    @app.context_processor
    def inject_globals():
        return {
            "makerspace_name": cfg.makerspace_name,
            "session_timeout": cfg.session_timeout_seconds,
        }

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        """JSON (not an HTML 500 page) for API routes so the frontend can show a
        useful message. Real HTTP errors (404 etc.) pass through."""
        if isinstance(e, HTTPException):
            return e
        logger.exception("Unhandled error on %s", request.path)
        if request.path.startswith("/api/"):
            return jsonify(error=f"Server error: {e}"), 500
        return f"Server error: {e}", 500

    # ---- the gate --------------------------------------------------------

    @app.before_request
    def require_session():
        """One check in front of everything, so a new route is private by default.

        Being signed in is what counts as activity, so this is also where the
        idle timer is pushed back.
        """
        endpoint = request.endpoint
        if endpoint is None or endpoint in PUBLIC_ENDPOINTS:
            return None

        who = gate.current()
        if not who:
            if request.path.startswith("/api/"):
                return jsonify(
                    error="Your session ended. Swipe your card to sign in again.",
                    need_login=True,
                ), 401
            return redirect(url_for("index"))

        if not who["is_staff"] and (
            endpoint == "admin" or request.path.startswith("/api/admin/")
        ):
            logger.warning("Denied admin to %s (not staff)", who["cruzid"])
            if request.path.startswith("/api/"):
                return jsonify(error="Inventory admin is staff only."), 403
            return render_template("denied.html", who=who, gate=gate), 403

        gate.touch()
        return None

    # ---- pages -----------------------------------------------------------

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/admin")
    def admin():
        return render_template("admin.html")

    # ---- session API -----------------------------------------------------

    @app.route("/api/session")
    def api_session():
        """Who is signed in, and how long they have left.

        Deliberately public and read-only: the page polls it to decide whether
        to show the sign-in screen, and polling must not itself count as
        activity or nobody would ever time out.
        """
        who = gate.current()
        return jsonify(
            signed_in=bool(who),
            user=who,
            timeout_seconds=gate.timeout,
            remaining=round(gate.remaining()) if who else 0,
            swipe_enabled=resolver.available,
            admin_requires_card=gate.admin_requires_card,
        )

    @app.route("/api/login", methods=["POST"])
    def api_login():
        data = request.get_json(force=True, silent=True) or {}
        who, error = gate.sign_in(data.get("swipe"), data.get("name"))
        if error:
            return jsonify(ok=False, error=error), 400
        return jsonify(ok=True, user=who, timeout_seconds=gate.timeout)

    @app.route("/api/logout", methods=["POST"])
    def api_logout():
        gate.sign_out()
        return jsonify(ok=True)

    @app.route("/api/keepalive", methods=["POST"])
    def api_keepalive():
        """Pushed by the page while someone is actually touching it.

        before_request has already refreshed the timer by the time this runs;
        the response just tells the page how long is left.
        """
        return jsonify(ok=True, remaining=round(gate.remaining()))

    # ---- catalog API -----------------------------------------------------

    @app.route("/api/catalog")
    def api_catalog():
        if not store.spreadsheet_id:
            return jsonify(error="No spreadsheet configured. Run `./checkout bootstrap` first."), 503
        return jsonify(
            items=store.get_items(),
            keys=store.get_keys(),
            consumables=store.get_consumables(),
            categories=store.get_categories(),
            default_checkout_days=store.default_days,
        )

    @app.route("/api/checkouts")
    def api_checkouts():
        """Your own checkouts. Staff may look up anyone's."""
        who = gate.current()
        active_only = request.args.get("active") == "1"
        if who["is_staff"]:
            cruzid = request.args.get("cruzid") or None
        else:
            cruzid = who["cruzid"]
        return jsonify(
            checkouts=store.get_checkouts(active_only=active_only, cruzid=cruzid)
        )

    # ---- checkout / return ----------------------------------------------

    @app.route("/api/checkout", methods=["POST"])
    def api_checkout():
        """Check the cart out to whoever is signed in.

        The name and CruzID come from the session, never from the request body:
        that is the whole point of signing in at the start of the visit.
        """
        who = gate.current()
        data = request.get_json(force=True, silent=True) or {}
        lines = data.get("lines") or []

        if not data.get("acknowledged"):
            return jsonify(error="You must accept the responsibility agreement to check out."), 400
        if not lines:
            return jsonify(error="Your cart is empty."), 400

        person_name, cruzid = who["name"], who["cruzid"]
        results = []
        for line in lines:
            kind = line.get("kind")
            ref_id = line.get("ref_id")
            qty = line.get("qty", 1)
            try:
                if kind == "consumable":
                    record = store.take_consumable(ref_id, qty, person_name, cruzid)
                else:
                    record = store.checkout(kind, ref_id, qty, person_name, cruzid)
                results.append({"ok": True, "ref_id": ref_id, "checkout": record})
            except (ValueError, LookupError) as e:
                results.append({"ok": False, "ref_id": ref_id, "error": str(e)})

        any_ok = any(r["ok"] for r in results)
        return jsonify(results=results), (200 if any_ok else 400)

    @app.route("/api/return", methods=["POST"])
    def api_return():
        who = gate.current()
        data = request.get_json(force=True, silent=True) or {}
        checkout_id = data.get("checkout_id")
        if not checkout_id:
            return jsonify(error="Missing checkout_id."), 400
        # Staff run the returns desk, so they may return anyone's checkout.
        owner = None if who["is_staff"] else who["cruzid"]
        try:
            record = store.return_checkout(checkout_id, owner_cruzid=owner)
            return jsonify(ok=True, checkout=record)
        except (ValueError, LookupError) as e:
            return jsonify(error=str(e)), 400

    # ---- admin API (staff only; enforced in require_session) --------------

    @app.route("/api/admin/item", methods=["POST"])
    def api_admin_item():
        data = request.get_json(force=True, silent=True) or {}
        try:
            record = {
                "item_id": data.get("item_id", ""),
                "name": (data.get("name") or "").strip(),
                "category": (data.get("category") or "").strip(),
                "description": (data.get("description") or "").strip(),
                "icon": (data.get("icon") or "📦").strip(),
                "location": (data.get("location") or "").strip(),
                "total_qty": int(data.get("total_qty") or 0),
                "available_qty": int(data.get("available_qty") or data.get("total_qty") or 0),
                "checkout_days": int(data.get("checkout_days") or store.default_days),
            }
        except (TypeError, ValueError):
            return jsonify(error="Quantities and checkout_days must be numbers."), 400
        if not record["name"]:
            return jsonify(error="Item name is required."), 400
        store.upsert_item(record)
        return jsonify(ok=True, item=record)

    @app.route("/api/admin/key", methods=["POST"])
    def api_admin_key():
        data = request.get_json(force=True, silent=True) or {}
        try:
            record = {
                "key_id": data.get("key_id", ""),
                "room": (data.get("room") or "").strip(),
                "description": (data.get("description") or "").strip(),
                "icon": (data.get("icon") or "🗝️").strip(),
                "total_qty": int(data.get("total_qty") or 0),
                "available_qty": int(data.get("available_qty") or data.get("total_qty") or 0),
                "checkout_days": int(data.get("checkout_days") or store.default_days),
            }
        except (TypeError, ValueError):
            return jsonify(error="Quantities and checkout_days must be numbers."), 400
        if not record["room"]:
            return jsonify(error="Room name is required."), 400
        store.upsert_key(record)
        return jsonify(ok=True, key=record)

    @app.route("/api/admin/consumable", methods=["POST"])
    def api_admin_consumable():
        data = request.get_json(force=True, silent=True) or {}
        try:
            record = {
                "consumable_id": data.get("consumable_id", ""),
                "name": (data.get("name") or "").strip(),
                "category": (data.get("category") or "").strip(),
                "description": (data.get("description") or "").strip(),
                "icon": (data.get("icon") or "🧤").strip(),
                "location": (data.get("location") or "").strip(),
                "unit": (data.get("unit") or "each").strip(),
                "stock_qty": int(data.get("stock_qty") or 0),
                "low_threshold": int(data.get("low_threshold") or 0),
            }
        except (TypeError, ValueError):
            return jsonify(error="Stock and threshold must be numbers."), 400
        if not record["name"]:
            return jsonify(error="Consumable name is required."), 400
        store.upsert_consumable(record)
        return jsonify(ok=True, consumable=record)

    return app


def run(host="127.0.0.1", port=5002, debug=False):
    cfg = config_module.load()
    logger.info("Starting checkout app on %s:%s (sheet %s)", host, port, cfg.spreadsheet_id or "UNSET")
    create_app(cfg).run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run(debug=os.environ.get("CHECKOUT_DEBUG") == "1")
