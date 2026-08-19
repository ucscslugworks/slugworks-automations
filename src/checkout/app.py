"""Flask web app for the makerspace checkout system.

Home Depot-styled catalog + cart. Instead of buying, you check items and room
keys out to your name with a due date, and take single-use supplies. Data lives
in a Google Sheet (see store.py / bootstrap.py).
"""

import os

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from src import log
from src.checkout import config as config_module
from src.checkout import identity
from src.checkout.store import SheetStore

logger = log.setup_logs("checkout", log.INFO)


def create_app(cfg=None):
    cfg = cfg or config_module.load()
    store = SheetStore(cfg, allow_auth=False)
    # Resolves swiped ID cards -> CruzID from the cached Canvas roster
    # (built by `./checkout roster`). Reloads itself when that cache changes.
    resolver = identity.Resolver()

    app = Flask(__name__)  # templates/ and static/ are alongside this module

    @app.context_processor
    def inject_globals():
        return {"makerspace_name": cfg.makerspace_name}

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

    # ---- pages -----------------------------------------------------------

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/admin")
    def admin():
        return render_template("admin.html")

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
            swipe_enabled=resolver.available,
        )

    @app.route("/api/resolve")
    def api_resolve():
        """Map a swiped ID card (or typed CruzID/SIS number) to a student.

        Returns {ok, cruzid, name}. Never echoes the SIS number back.
        """
        swipe = request.args.get("swipe", "")
        if not resolver.available:
            return jsonify(
                ok=False,
                error="ID lookup isn't set up yet. Run `./checkout roster` to build it from Canvas.",
            ), 503
        match = resolver.resolve(swipe)
        if not match:
            return jsonify(ok=False, error="Card not recognized. Enter your CruzID manually."), 404
        return jsonify(ok=True, cruzid=match["cruzid"], name=match["name"])

    @app.route("/api/checkouts")
    def api_checkouts():
        active_only = request.args.get("active") == "1"
        cruzid = request.args.get("cruzid") or None
        return jsonify(
            checkouts=store.get_checkouts(active_only=active_only, cruzid=cruzid)
        )

    # ---- checkout / return ----------------------------------------------

    @app.route("/api/checkout", methods=["POST"])
    def api_checkout():
        data = request.get_json(force=True, silent=True) or {}
        person_name = (data.get("person_name") or "").strip()
        cruzid = (data.get("cruzid") or "").strip()
        lines = data.get("lines") or []

        if not data.get("acknowledged"):
            return jsonify(error="You must accept the responsibility agreement to check out."), 400
        if not person_name:
            return jsonify(error="Please enter your name."), 400
        if not cruzid:
            return jsonify(error="Please enter your CruzID."), 400
        if not lines:
            return jsonify(error="Your cart is empty."), 400

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
        data = request.get_json(force=True, silent=True) or {}
        checkout_id = data.get("checkout_id")
        if not checkout_id:
            return jsonify(error="Missing checkout_id."), 400
        try:
            record = store.return_checkout(checkout_id)
            return jsonify(ok=True, checkout=record)
        except (ValueError, LookupError) as e:
            return jsonify(error=str(e)), 400

    # ---- admin API -------------------------------------------------------

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
