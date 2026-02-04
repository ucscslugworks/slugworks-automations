"""
Flask dashboard for Bambu Lab printer management.
Routes:
  /dashboard - Home page
  /dashboard/printers - Control printers (stop prints)
  /dashboard/prints - View prints with cloud photos
  /dashboard/users - Manage user limits, exemptions, bans
  /dashboard/inventory - View & manage filament inventory
"""

import json
import os
import sqlite3
import smtplib
import traceback
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from io import BytesIO

import requests
from flask import Flask, render_template, request, jsonify, send_file

from src import constants, log
from src.bambu_printers import bambu_db, bambu_account

logger = log.setup_logs("dashboard", additional_handlers=[("bambu", log.INFO)])

DASHBOARD_OBJECT = None
DASHBOARD_STARTED = False

# Filament inventory DB
INVENTORY_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "common", "inventory.db"
)

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
        self.db = bambu_db.BambuDB()
        self.account = bambu_account.BambuAccount()
        self.init_inventory_db()
        self.register_routes()

    def init_inventory_db(self):
        """Initialize filament inventory database."""
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
        @self.app.route("/dashboard")
        def home():
            return render_template("dashboard_home.html")

        @self.app.route("/dashboard/printers")
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
        def cancel_print(printer_name):
            try:
                from src.bambu_printers import get_printer

                devices = self.account.get_devices()
                if printer_name not in devices:
                    return jsonify({"error": "Printer not found"}), 404

                printer = get_printer(printer_name, devices[printer_name])
                printer.cancel()
                logger.info(f"cancel_print: Canceled print on {printer_name}")
                return jsonify({"success": True})
            except Exception as e:
                logger.error(f"cancel_print: {traceback.format_exc()}")
                return jsonify({"error": str(e)}), 500

        @self.app.route("/dashboard/prints")
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

        @self.app.route("/dashboard/users/update", methods=["POST"])
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
        """Download print photo from URL and save locally."""
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
        """Load ban and exemption lists from common/."""
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
        """Add or remove cruzid from exemption list."""
        base_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "common"
        )
        exempt_path = os.path.join(base_dir, "exemption.json")

        try:
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
        except Exception:
            logger.error(f"toggle_exemption: {traceback.format_exc()}")

    def toggle_ban(self, cruzid, enable):
        """Add or remove cruzid from ban list."""
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
        """Check stock levels and email staff if < 5 packages remaining."""
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
        """Send email alert when stock is low."""
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
    dashboard.run(debug=True)
