# flask dashboard for bambu printer management
# routes:
#   /dashboard - home page
#   /dashboard/printers - control printers (stop prints)
#   /dashboard/prints - view prints with cloud photos
#   /dashboard/users - manage user limits, exemptions, bans
#   /dashboard/inventory - view & manage filament inventory

import json
import os
import sqlite3
import smtplib
import traceback
from functools import wraps
from glob import glob
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from io import BytesIO

import requests
from authlib.integrations.flask_client import OAuth
from flask import Flask, render_template, request, jsonify, send_file, redirect, session

from src import constants, log, staff_cache
from src.bambu_printers import bambu_db, bambu_account

logger = log.setup_logs("dashboard", additional_handlers=[("bambu", log.INFO)])

DASHBOARD_OBJECT = None
DASHBOARD_STARTED = False

# Filament inventory DB
INVENTORY_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "common", "inventory.db"
)
AUTH_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "common", "dashboard_auth.json"
)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

# Photo storage
PHOTO_DIR = "/data/prints"
os.makedirs(PHOTO_DIR, exist_ok=True)


def get_dashboard():
    global DASHBOARD_OBJECT, DASHBOARD_STARTED
    if not DASHBOARD_STARTED:
        DASHBOARD_STARTED = True
        DASHBOARD_OBJECT = Dashboard()
        logger.info("get_dashboard: Created new Dashboard object")
    else:
        while DASHBOARD_OBJECT is None:
            import time

            time.sleep(1)
        logger.info("get_dashboard: Retrieved existing Dashboard object")
    return DASHBOARD_OBJECT


class Dashboard:
    def __init__(self):
        template_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "templates"
        )
        static_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "static"
        )
        os.makedirs(template_dir, exist_ok=True)
        os.makedirs(static_dir, exist_ok=True)

        self.app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
        self.auth_config = self.load_auth_config()
        self.app.secret_key = self.auth_config.get("secret_key") or os.urandom(32)
        self.app.config["SESSION_COOKIE_HTTPONLY"] = True
        self.app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
        if self.auth_config.get("cookie_secure") is True:
            self.app.config["SESSION_COOKIE_SECURE"] = True
        if not self.auth_config.get("secret_key"):
            logger.warning("dashboard auth: secret_key not set; using a temporary key")

        self.oauth = OAuth(self.app)
        self.google_oauth_ready = self.setup_google_oauth()
        self.db = bambu_db.BambuDB()
        self.account = bambu_account.BambuAccount()
        self.init_inventory_db()
        self.register_routes()

    def load_auth_config(self):
        config = {
            "allowed_emails": [],
            "secret_key": None,
            "client_id": None,
            "client_secret": None,
            "client_secret_path": None,
            "redirect_uri": None,
            "cookie_secure": False,
        }
        if os.path.exists(AUTH_CONFIG_PATH):
            try:
                with open(AUTH_CONFIG_PATH, "r", encoding="utf-8") as f:
                    file_config = json.load(f)
                config.update({k: v for k, v in file_config.items() if v is not None})
            except Exception:
                logger.error("dashboard auth: failed to read dashboard_auth.json")
        env_allowed = os.getenv("DASHBOARD_ALLOWED_EMAILS")
        if env_allowed:
            config["allowed_emails"] = [e.strip() for e in env_allowed.split(",") if e.strip()]
        config["secret_key"] = config["secret_key"] or os.getenv("DASHBOARD_SECRET_KEY")
        config["client_id"] = config["client_id"] or os.getenv("DASHBOARD_GOOGLE_CLIENT_ID")
        config["client_secret"] = config["client_secret"] or os.getenv("DASHBOARD_GOOGLE_CLIENT_SECRET")
        config["redirect_uri"] = config["redirect_uri"] or os.getenv("DASHBOARD_GOOGLE_REDIRECT_URI")
        config["client_secret_path"] = config["client_secret_path"] or os.getenv("DASHBOARD_GOOGLE_CLIENT_SECRET_PATH")
        cookie_secure = os.getenv("DASHBOARD_COOKIE_SECURE")
        if cookie_secure is not None:
            config["cookie_secure"] = cookie_secure.lower() in ("1", "true", "yes")
        config["allowed_emails"] = [e.lower() for e in config.get("allowed_emails", []) if e]
        return config

    def load_google_client(self):
        client_id = self.auth_config.get("client_id")
        client_secret = self.auth_config.get("client_secret")
        if client_id and client_secret:
            return client_id, client_secret
        secret_path = self.auth_config.get("client_secret_path")
        candidate_paths = []
        if secret_path:
            candidate_paths.append(secret_path)
        candidate_paths.extend(glob(os.path.join(REPO_ROOT, "client_secret_*.json")))
        for path in candidate_paths:
            if not path or not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                payload = data.get("web") or data.get("installed") or {}
                cid = payload.get("client_id")
                csecret = payload.get("client_secret")
                if cid and csecret:
                    return cid, csecret
            except Exception:
                logger.error(f"dashboard auth: failed to read google client file {path}")
        return None, None

    def setup_google_oauth(self):
        client_id, client_secret = self.load_google_client()
        if not client_id or not client_secret:
            logger.error("dashboard auth: missing Google OAuth client_id/client_secret")
            return False
        self.oauth.register(
            name="google",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        return True

    def is_allowed_email(self, email):
        allowed = self.auth_config.get("allowed_emails", [])
        if not allowed:
            return False
        return email.lower() in allowed

    def login_required(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not session.get("user_email"):
                return redirect("/dashboard/login")
            return func(*args, **kwargs)
        return wrapper

    def init_inventory_db(self):
        # initialize the filament inventory database
        conn = sqlite3.connect(INVENTORY_DB)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY,
                filament_type TEXT,
                color TEXT,
                quantity_packages INTEGER,
                cost_per_package REAL,
                added_date TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS filament_moves (
                id INTEGER PRIMARY KEY,
                filament_id INTEGER,
                printer TEXT,
                ams_slot INTEGER,
                quantity_packages INTEGER,
                move_type TEXT,
                timestamp TEXT,
                FOREIGN KEY (filament_id) REFERENCES inventory (id)
            )
        """
        )
        conn.commit()
        conn.close()

    def register_routes(self):
        @self.app.before_request
        def require_login():
            if not request.path.startswith("/dashboard"):
                return None
            if request.path.startswith("/static/"):
                return None
            if request.path in (
                "/dashboard/login",
                "/dashboard/auth/callback",
                "/dashboard/logout",
            ):
                return None
            if not session.get("user_email"):
                return redirect("/dashboard/login")
            return None

        @self.app.route("/dashboard/login")
        def login():
            if not self.google_oauth_ready:
                return render_template(
                    "error.html",
                    message="Google login not configured. Add dashboard_auth.json or environment variables.",
                ), 500
            nonce = os.urandom(16).hex()
            session["oauth_nonce"] = nonce
            redirect_uri = self.auth_config.get("redirect_uri")
            if not redirect_uri:
                redirect_uri = request.host_url.rstrip("/") + "/dashboard/auth/callback"
            return self.oauth.google.authorize_redirect(redirect_uri, nonce=nonce)

        @self.app.route("/dashboard/auth/callback")
        def auth_callback():
            try:
                token = self.oauth.google.authorize_access_token()
                nonce = session.pop("oauth_nonce", None)
                user = self.oauth.google.parse_id_token(token, nonce=nonce)
                email = (user or {}).get("email", "").lower()
                if not email:
                    logger.warning("dashboard auth: login failed (missing email)")
                    return render_template("error.html", message="Login failed."), 403
                if not self.is_allowed_email(email):
                    logger.warning(
                        f"dashboard auth: denied email={email} ip={request.remote_addr}"
                    )
                    return render_template(
                        "error.html",
                        message="Your account is not authorized to access this dashboard.",
                    ), 403
                user_name = (user or {}).get("name") or email
                session["user_email"] = email
                session["user_name"] = user_name
                logger.info(
                    f"dashboard auth: login success name={user_name} email={email} ip={request.remote_addr}"
                )
                return redirect("/dashboard")
            except Exception:
                logger.error(f"dashboard auth: callback error {traceback.format_exc()}")
                return render_template("error.html", message="Login failed."), 500

        @self.app.route("/dashboard/logout")
        def logout():
            email = session.get("user_email")
            session.clear()
            if email:
                logger.info(
                    f"dashboard auth: logout email={email} ip={request.remote_addr}"
                )
            return redirect("/dashboard/login")

        @self.app.route("/dashboard")
        @self.login_required
        def home():
            return render_template("dashboard_home.html")

        @self.app.route("/dashboard/printers")
        @self.login_required
        def printers():
            try:
                devices = self.account.get_devices()
                printer_data = {}
                for name in devices:
                    pdata = self.db.get_printer_data(name)
                    printer_data[name] = pdata
                logger.info(f"printers: Retrieved {len(printer_data)} printers")
                return render_template("dashboard_printers.html", printers=printer_data)
            except Exception:
                logger.error(f"printers: {traceback.format_exc()}")
                return render_template(
                    "error.html", message="Failed to load printers"
                ), 500

        @self.app.route("/dashboard/printers/cancel/<printer_name>", methods=["POST"])
        @self.login_required
        def cancel_print(printer_name):
            try:
                from src.bambu_printers import get_printer

                devices = self.account.get_devices()
                if printer_name not in devices:
                    logger.error(f"cancel_print: Printer {printer_name} not found")
                    return jsonify({"error": "Printer not found"}), 404

                device_info = devices[printer_name]
                logger.info(f"cancel_print: Getting printer object for {printer_name}")
                printer = get_printer(printer_name, device_info)

                if not printer:
                    logger.error(f"cancel_print: Failed to instantiate printer {printer_name}")
                    return jsonify({"error": "Failed to connect to printer"}), 500

                logger.info(f"cancel_print: Calling cancel() on {printer_name}")
                result = printer.cancel()
                logger.info(f"cancel_print: Cancel result for {printer_name}: {result}")
                return jsonify({"success": True, "result": str(result)})
            except Exception as e:
                logger.error(f"cancel_print: {traceback.format_exc()}")
                return jsonify({"error": str(e)}), 500

        @self.app.route("/dashboard/prints")
        @self.login_required
        def prints_view():
            try:
                # Get both current and archived prints
                current = self.db.get_current_prints()
                archive = self.db.get_print_archive()

                # Combine and sort by print ID (descending for newest first)
                all_prints = list(current) + list(archive)
                all_prints.sort(key=lambda x: x[0], reverse=True)
                all_prints = all_prints[:100]

                # Eagerly download photos from active prints (cloud links expire fast)
                for print_row in all_prints:
                    print_id = print_row[0]
                    photo_path = os.path.join(PHOTO_DIR, f"{print_id}.jpg")
                    if not os.path.exists(photo_path):
                        try:
                            # Try to get from prints_current first (hot link)
                            cover_url = None
                            conn = sqlite3.connect(
                                os.path.join(
                                    os.path.dirname(os.path.abspath(__file__)),
                                    "bambu.db",
                                )
                            )
                            cursor = conn.cursor()
                            result = cursor.execute(
                                "SELECT cover FROM prints_current WHERE id = ?",
                                (print_id,),
                            ).fetchone()
                            if result:
                                cover_url = result[0]

                            # Fall back to archive
                            if not cover_url:
                                result = cursor.execute(
                                    "SELECT cover FROM prints_archive WHERE id = ?",
                                    (print_id,),
                                ).fetchone()
                                if result:
                                    cover_url = result[0]

                            conn.close()

                            if cover_url:
                                self.download_photo(cover_url, print_id)
                                logger.debug(
                                    f"prints_view: Downloaded photo for print {print_id}"
                                )
                        except Exception as e:
                            logger.debug(f"prints_view: Failed to fetch photo for {print_id}: {e}")

                logger.info(f"prints_view: Retrieved {len(all_prints)} prints (current + archive)")
                return render_template("dashboard_prints.html", prints=all_prints)
            except Exception:
                logger.error(f"prints_view: {traceback.format_exc()}")
                return render_template(
                    "error.html", message="Failed to load prints"
                ), 500

        @self.app.route("/dashboard/prints/photo/<int:print_id>")
        @self.login_required
        def get_photo(print_id):
            try:
                photo_path = os.path.join(PHOTO_DIR, f"{print_id}.jpg")
                if os.path.exists(photo_path):
                    return send_file(photo_path, mimetype="image/jpeg")
                return jsonify({"error": "Photo not found"}), 404
            except Exception:
                logger.error(f"get_photo: {traceback.format_exc()}")
                return jsonify({"error": "Failed to load photo"}), 500

        @self.app.route("/dashboard/users")
        @self.login_required
        def users():
            try:
                exemptions, bans = self.load_policy_lists()
                limits = self.db.get_limits_snapshot()
                logger.info(f"users: Retrieved {len(limits)} users")
                return render_template(
                    "dashboard_users.html",
                    limits=limits,
                    exemptions=exemptions,
                    bans=bans,
                )
            except Exception:
                logger.error(f"users: {traceback.format_exc()}")
                return render_template(
                    "error.html", message="Failed to load users"
                ), 500
        @self.app.route("/dashboard/api/printers")
        @self.login_required
        def api_printers():
            try:
                devices = self.account.get_devices()
                logger.info(f"api_printers: Got {len(devices)} devices: {list(devices.keys())}")
                printer_data = {}
                for name in devices:
                    try:
                        pdata = self.db.get_printer_data(name)
                        if pdata:
                            status = pdata.get("status", 0)
                            printer_data[name] = {
                                "name": name,
                                "status": status,
                                "status_text": ["Offline", "Idle", "Unmatched", "Printing"][status] if 0 <= status <= 3 else "Unknown",
                                "current_print_id": pdata.get("print_id"),
                                "cruzid": pdata.get("cruzid"),
                                "gcode_file": pdata.get("gcode_file"),
                                "percent_complete": pdata.get("percent_complete"),
                                "time_remaining": pdata.get("time_remaining"),
                                "current_layer": pdata.get("current_layer"),
                                "layer_count": pdata.get("layer_count"),
                                "tool_temp": pdata.get("tool_temp"),
                                "tool_temp_target": pdata.get("tool_temp_target"),
                                "bed_temp": pdata.get("bed_temp"),
                                "bed_temp_target": pdata.get("bed_temp_target"),
                            }
                    except Exception as e:
                        logger.error(f"api_printers: Error getting data for {name}: {e}")
                logger.info(f"api_printers: Returning {len(printer_data)} printers")
                return jsonify(printer_data)
            except Exception as e:
                logger.error(f"api_printers: {e}: {traceback.format_exc()}")
                return jsonify({"error": str(e)}), 500

        @self.app.route("/dashboard/api/users")
        @self.login_required
        def api_users():
            try:
                exemptions, bans = self.load_policy_lists()
                staff = staff_cache.read()

                # Get current limits column name
                from datetime import datetime
                column = f"weight_{datetime.now().year}_{(datetime.now().month - 1) // 3}"

                # Query directly from DB to avoid recursive cursor issues
                conn = sqlite3.connect(os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), "bambu.db"
                ))
                cursor = conn.cursor()

                # Get limits
                cursor.execute(f"SELECT cruzid, {column} FROM limits")
                limits = cursor.fetchall()

                # Get usage (sum of weights from prints_archive)
                cursor.execute("SELECT cruzid, SUM(weight) FROM prints_archive GROUP BY cruzid")
                usage_rows = cursor.fetchall()
                usage_map = {row[0]: row[1] if row[1] is not None else 0 for row in usage_rows}

                conn.close()

                users = []
                for row in limits:
                    cruzid = row[0]
                    current_limit = row[1] if row[1] is not None else 1000
                    usage = usage_map.get(cruzid, 0)
                    users.append({
                        "cruzid": cruzid,
                        "current_limit": current_limit,
                        "usage": usage,
                        "exempt": cruzid in exemptions,
                        # exempt because they are staff, not because someone
                        # ticked the box: the checkbox cannot take this away
                        "staff": cruzid in staff,
                        "banned": cruzid in bans,
                    })
                return jsonify(users)
            except Exception:
                logger.error(f"api_users: {traceback.format_exc()}")
                return jsonify([]), 500

        @self.app.route("/dashboard/api/inventory")
        @self.login_required
        def api_inventory():
            try:
                conn = sqlite3.connect(INVENTORY_DB)
                cursor = conn.cursor()
                stock = cursor.execute(
                    "SELECT * FROM inventory ORDER BY filament_type"
                ).fetchall()
                moves = cursor.execute(
                    "SELECT * FROM filament_moves ORDER BY timestamp DESC LIMIT 50"
                ).fetchall()
                conn.close()

                stock_data = [
                    {
                        "id": row[0],
                        "filament_type": row[1],
                        "color": row[2],
                        "quantity_packages": row[3],
                        "cost_per_package": row[4],
                        "added_date": row[5],
                    }
                    for row in stock
                ]
                moves_data = [
                    {
                        "id": row[0],
                        "filament_id": row[1],
                        "printer": row[2],
                        "ams_slot": row[3],
                        "quantity_packages": row[4],
                        "move_type": row[5],
                        "timestamp": row[6],
                    }
                    for row in moves
                ]
                return jsonify({"stock": stock_data, "moves": moves_data})
            except Exception:
                logger.error(f"api_inventory: {traceback.format_exc()}")
                return jsonify({"stock": [], "moves": []}), 500

        @self.app.route("/dashboard/users/update", methods=["POST"])
        @self.login_required
        def update_user():
            try:
                data = request.json
                cruzid = data.get("cruzid")
                action = data.get("action")  # "limit", "exempt", "ban"
                value = data.get("value")

                if action == "limit":
                    # Update filament limit (add/subtract)
                    self.db.subtract_limit(cruzid, -value)
                    logger.info(f"update_user: Updated {cruzid} limit by {value}g")
                elif action == "exempt":
                    # Toggle exemption
                    self.toggle_exemption(cruzid, value)
                    logger.info(f"update_user: Set {cruzid} exempt={value}")
                elif action == "ban":
                    # Toggle ban
                    self.toggle_ban(cruzid, value)
                    logger.info(f"update_user: Set {cruzid} ban={value}")

                return jsonify({"success": True})
            except Exception as e:
                logger.error(f"update_user: {traceback.format_exc()}")
                return jsonify({"error": str(e)}), 500

        @self.app.route("/dashboard/inventory")
        @self.login_required
        def inventory():
            try:
                conn = sqlite3.connect(INVENTORY_DB)
                cursor = conn.cursor()
                stock = cursor.execute(
                    "SELECT * FROM inventory ORDER BY filament_type"
                ).fetchall()
                moves = cursor.execute(
                    "SELECT * FROM filament_moves ORDER BY timestamp DESC LIMIT 50"
                ).fetchall()
                conn.close()

                devices = self.account.get_devices()
                printer_data = {}
                for name in devices:
                    pdata = self.db.get_printer_data(name)
                    printer_data[name] = pdata

                logger.info(f"inventory: Retrieved {len(stock)} stock items")
                return render_template(
                    "dashboard_inventory.html",
                    stock=stock,
                    moves=moves,
                    printers=list(devices.keys()),
                    printer_data=printer_data,
                )
            except Exception:
                logger.error(f"inventory: {traceback.format_exc()}")
                return render_template(
                    "error.html", message="Failed to load inventory"
                ), 500

        @self.app.route("/dashboard/inventory/add", methods=["POST"])
        @self.login_required
        def add_stock():
            try:
                data = request.json
                filament_type = "PLA"
                color = data.get("color")
                quantity = int(data.get("quantity"))

                conn = sqlite3.connect(INVENTORY_DB)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO inventory (filament_type, color, quantity_packages, added_date) VALUES (?, ?, ?, ?)",
                    (filament_type, color, quantity, datetime.now().isoformat()),
                )
                conn.commit()
                conn.close()

                logger.info(f"add_stock: Added {quantity} packages of {color} {filament_type}")
                return jsonify({"success": True})
            except Exception as e:
                logger.error(f"add_stock: {traceback.format_exc()}")
                return jsonify({"error": str(e)}), 500

        @self.app.route("/dashboard/inventory/move", methods=["POST"])
        @self.login_required
        def move_filament():
            try:
                data = request.json
                filament_id = int(data.get("filament_id"))
                printer = data.get("printer")
                ams_slot = int(data.get("ams_slot"))
                quantity = int(data.get("quantity"))

                conn = sqlite3.connect(INVENTORY_DB)
                cursor = conn.cursor()

                # Subtract from stock
                cursor.execute(
                    "UPDATE inventory SET quantity_packages = quantity_packages - ? WHERE id = ?",
                    (quantity, filament_id),
                )

                # Log the move
                cursor.execute(
                    "INSERT INTO filament_moves (filament_id, printer, ams_slot, quantity_packages, move_type, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        filament_id,
                        printer,
                        ams_slot,
                        quantity,
                        "to_printer",
                        datetime.now().isoformat(),
                    ),
                )

                conn.commit()
                conn.close()

                logger.info(
                    f"move_filament: Moved {quantity} packages to {printer} AMS slot {ams_slot}"
                )

                # Check stock levels and send alert if low
                self.check_and_alert_stock()

                return jsonify({"success": True})
            except Exception as e:
                logger.error(f"move_filament: {traceback.format_exc()}")
                return jsonify({"error": str(e)}), 500

    def download_photo(self, url, print_id):
        # download a print photo from the url and save it locally
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                photo_path = os.path.join(PHOTO_DIR, f"{print_id}.jpg")
                with open(photo_path, "wb") as f:
                    f.write(resp.content)
                logger.debug(f"download_photo: Saved photo for print {print_id}")
        except Exception:
            logger.warning(f"download_photo: Failed to download for {print_id}")

    def load_policy_lists(self):
        # load the ban and exemption lists from common/
        exemptions = set()
        bans = set()
        base_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "common"
        )

        for fname in ("bambu_limit_exempt.json", "exemption.json"):
            fpath = os.path.join(base_dir, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            exemptions.update([str(x) for x in data])
                except Exception:
                    pass

        # staff are exempt by standing, from the nightly common/staff.txt
        # refresh - same rule the manager enforces (see its load_policy_lists).
        exemptions.update(staff_cache.read())

        ban_path = os.path.join(base_dir, "ban.json")
        if os.path.exists(ban_path):
            try:
                with open(ban_path, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        bans.update([str(x) for x in data])
            except Exception:
                pass

        return exemptions, bans

    def toggle_exemption(self, cruzid, enable):
        # add or remove a cruzid from the exemption list
        base_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "common"
        )
        exempt_path = os.path.join(base_dir, "exemption.json")
        bambu_exempt_path = os.path.join(base_dir, "bambu_limit_exempt.json")

        try:
            # Update exemption.json
            if os.path.exists(exempt_path):
                with open(exempt_path, "r") as f:
                    exemptions = json.load(f)
            else:
                exemptions = []

            if enable:
                if cruzid not in exemptions:
                    exemptions.append(cruzid)
            else:
                if cruzid in exemptions:
                    exemptions.remove(cruzid)

            with open(exempt_path, "w") as f:
                json.dump(exemptions, f)

            # Also update bambu_limit_exempt.json if it exists
            if os.path.exists(bambu_exempt_path):
                with open(bambu_exempt_path, "r") as f:
                    bambu_exemptions = json.load(f)

                if enable:
                    if cruzid not in bambu_exemptions:
                        bambu_exemptions.append(cruzid)
                else:
                    if cruzid in bambu_exemptions:
                        bambu_exemptions.remove(cruzid)

                with open(bambu_exempt_path, "w") as f:
                    json.dump(bambu_exemptions, f)
        except Exception:
            logger.error(f"toggle_exemption: {traceback.format_exc()}")

    def toggle_ban(self, cruzid, enable):
        # add or remove a cruzid from the ban list
        base_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "common"
        )
        ban_path = os.path.join(base_dir, "ban.json")

        try:
            if os.path.exists(ban_path):
                with open(ban_path, "r") as f:
                    bans = json.load(f)
            else:
                bans = []

            if enable:
                if cruzid not in bans:
                    bans.append(cruzid)
            else:
                if cruzid in bans:
                    bans.remove(cruzid)

            with open(ban_path, "w") as f:
                json.dump(bans, f)
        except Exception:
            logger.error(f"toggle_ban: {traceback.format_exc()}")

    def check_and_alert_stock(self):
        # check stock levels and email staff if < 5 packages remaining
        try:
            conn = sqlite3.connect(INVENTORY_DB)
            cursor = conn.cursor()

            # Get total stock by type
            stock_by_type = cursor.execute(
                "SELECT filament_type, SUM(quantity_packages) FROM inventory GROUP BY filament_type"
            ).fetchall()

            conn.close()

            # Check for low stock
            low_stock_items = [
                (ftype, qty) for ftype, qty in stock_by_type if qty is not None and qty < 5
            ]

            if low_stock_items:
                self.send_low_stock_alert(low_stock_items)
                logger.warning(f"Low filament stock alert sent: {low_stock_items}")
        except Exception:
            logger.error(f"check_and_alert_stock: {traceback.format_exc()}")

    def send_low_stock_alert(self, low_stock_items):
        # send an email alert when stock is low
        try:
            # Read email config from common/bambu.json or use defaults
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "..", "common", "bambu.json"
            )

            email_from = "slugworks@ucsc.edu"
            email_to = "slugworks-staff@ucsc.edu"

            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    if "alert_email" in config:
                        email_to = config["alert_email"]
            except Exception:
                pass

            # Build email message
            subject = "⚠️ Low Filament Stock Alert"
            body = "The following filament types have less than 5 packages remaining:\n\n"

            for ftype, qty in low_stock_items:
                body += f"- {ftype}: {qty} packages\n"

            body += "\nPlease order more filament soon."

            # Send via Gmail (if configured) or local mail
            try:
                import smtplib
                from email.mime.text import MIMEText

                msg = MIMEText(body)
                msg["Subject"] = subject
                msg["From"] = email_from
                msg["To"] = email_to

                # Try Gmail SMTP
                server = smtplib.SMTP("smtp.gmail.com", 587)
                server.starttls()

                with open(config_path, "r") as f:
                    config = json.load(f)
                    if "email_password" in config:
                        server.login(email_from, config["email_password"])
                        server.send_message(msg)
                        server.quit()
                        logger.info(f"Low stock alert email sent to {email_to}")
                        return
            except Exception:
                pass

            # Fallback: try local mail
            try:
                server = smtplib.SMTP("localhost")
                server.send_message(msg)
                server.quit()
                logger.info(f"Low stock alert email sent to {email_to} via local mail")
            except Exception as e:
                logger.warning(f"Failed to send email alert: {e}")
        except Exception:
            logger.error(f"send_low_stock_alert: {traceback.format_exc()}")

    def run(self, host="0.0.0.0", port=5000, debug=False):
        logger.info(f"Dashboard starting on {host}:{port}")
        self.app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    dashboard = get_dashboard()
    dashboard.run(host="0.0.0.0", port=5001, debug=False)
