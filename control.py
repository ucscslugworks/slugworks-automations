import json
import os
import sqlite3
from datetime import datetime, timedelta
import time
import logging

import requests
from flask import Flask, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_socketio import SocketIO, emit
from oauthlib.oauth2 import WebApplicationClient
from threading import Thread, Event

# import control_nfc as nfc
import fake_nfc as nfc
import sheet
from db import init_db_command
from user import User

# Configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", sheet.creds.client_id)
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", sheet.creds.client_secret)
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
ALLOWED_EMAILS = {"chartier@ucsc.edu", "imadan1@ucsc.edu", "nkouatli@ucsc.edu"}

# Change directory to current file location
path = os.path.dirname(os.path.abspath(__file__))
os.chdir(path)

# Create a new directory for logs if it doesn't exist
if not os.path.exists(path + "/logs/control"):
    os.makedirs(path + "/logs/control")

# create new logger with all levels
logger = logging.getLogger("root")
logger.setLevel(logging.DEBUG)

# create file handler which logs debug messages (and above - everything)
fh = logging.FileHandler(f"logs/control/{str(datetime.now())}.log")
fh.setLevel(logging.DEBUG)

# create console handler which only logs warnings (and above)
ch = logging.StreamHandler()
ch.setLevel(logging.WARNING)

# create formatter and add it to the handlers
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s: %(message)s")
fh.setFormatter(formatter)
ch.setFormatter(formatter)

# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(12).hex()
socketio = SocketIO(app, cors_allowed_origins="*")
thread = None
thread_stop_event = Event()

sheet.get_sheet_data(limited=False)
alarm_enable_names = ["ENABLE", "DISABLE"]
device_status_names = ["ONLINE", "OFFLINE"]
status_colors = ["#3CBC8D", "red", ""]
alarm_status_names = ["OK", "ALARM", "TAGGED OUT", "DISABLED"]
alarm_status_colors = ["#3CBC8D", "red", "yellow", "gray", ""]

login_manager = LoginManager()
login_manager.init_app(app)

# Naive database setup
try:
    init_db_command()
    logger.info("Database initialized successfully.")
except sqlite3.OperationalError:
    # Assume it's already been created
    logger.warning("Database already exists. Skipping initialization.")

# OAuth 2 client setup
client = WebApplicationClient(GOOGLE_CLIENT_ID)


# Flask-Login helper to retrieve a user from our db
@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)


@login_manager.unauthorized_handler
def unauthorized():
    logger.warning("Unauthorized access attempt.")
    return redirect("/login")


def assign_uid(cruzid, overwrite, uid):
    added = False
    carderror = ""
    if sheet.get_uid(cruzid) == uid:
        carderror = f"Card is already assigned to {cruzid}"
        logger.debug(carderror)
    elif sheet.get_uid(cruzid) and sheet.get_cruzid(uid) and not overwrite:
        carderror = f"Card is already assigned to {sheet.get_cruzid(uid)}, and {cruzid} already has a card. If you would like to reassign the card to {cruzid} and replace {cruzid}'s existing card, please overwrite."
        logger.debug(carderror)
    elif sheet.get_uid(cruzid) and not overwrite:
        carderror = (
            f"{cruzid} already has a card, please overwrite to replace with this card"
        )
        logger.debug(carderror)
    elif sheet.get_cruzid(uid) and not overwrite:
        carderror = f"Card is already assigned to {sheet.get_cruzid(uid)}. If you would like to reassign the card to {cruzid}, please overwrite."
        logger.debug(carderror)
    else:
        sheet.set_uid(cruzid, uid, overwrite)
        sheet.run_in_thread(f=sheet.write_student_staff_sheets)
        carderror = f"Card added to database for {cruzid}"
        added = True
        logger.info(carderror)
    return carderror, added


CHECKIN_TIMEOUT = 30  # seconds


def update_data():
    sheet.get_canvas_status_sheet()
    if (
        not sheet.last_update_time
        or sheet.last_canvas_update_time > sheet.last_update_time
        or datetime.now() - sheet.last_update_time
        > timedelta(0, CHECKIN_TIMEOUT, 0, 0, 0, 0, 0)
    ):
        logger.info("Getting sheet data...")
        sheet.get_sheet_data()


def background_thread():
    while not thread_stop_event.is_set():
        try:
            logger.debug("Background thread updating data...")
            update_data()
            socketio.emit("update", {"message": "Data updated"})
            logger.info("Data updated and event emitted.")
            time.sleep(30)  # 30 seconds interval
        except Exception as e:
            logger.error(f"Error during background update: {e}")


@app.route("/")
def index():
    if current_user.is_authenticated:
        logger.debug("Rendering index page for authenticated user.")
        return (
            "<p>Hello, you're logged in as {}! Email: {}</p>"
            "<a class='button' href='/dashboard'>Dashboard</a><br>"
            '<a class="button" href="/logout">Logout</a>'.format(
                current_user.name, current_user.email
            )
        )
    else:
        logger.debug("Rendering index page for unauthenticated user.")
        return '<a class="button" href="/login">Google Login</a>'


def get_google_provider_cfg():
    logger.debug("Fetching Google provider configuration.")
    return requests.get(GOOGLE_DISCOVERY_URL).json()


@app.route("/login")
def login():
    google_provider_cfg = get_google_provider_cfg()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]

    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=request.base_url + "/callback",
        scope=["openid", "email", "profile"],
    )
    logger.debug("Redirecting to Google's OAuth 2.0 authorization endpoint.")
    return redirect(request_uri)


@app.route("/login/callback")
def callback():
    code = request.args.get("code")
    google_provider_cfg = get_google_provider_cfg()
    token_endpoint = google_provider_cfg["token_endpoint"]

    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=request.base_url,
        code=code,
    )
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
    )

    client.parse_request_body_response(json.dumps(token_response.json()))

    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)

    if userinfo_response.json().get("email_verified"):
        unique_id = userinfo_response.json()["sub"]
        users_email = userinfo_response.json()["email"]
        picture = userinfo_response.json()["picture"]
        users_name = userinfo_response.json()["given_name"]
        logger.info(f"User {users_email} authenticated successfully.")

        # Check if email is allowed
        if users_email not in ALLOWED_EMAILS:
            logger.warning(f"Unauthorized login attempt by {users_email}.")
            return "Unauthorized user", 403

    else:
        logger.error("User email not available or not verified by Google.")
        return "User email not available or not verified by Google.", 400

    user = User(id_=unique_id, name=users_name, email=users_email, profile_pic=picture)

    if not User.get(unique_id):
        User.create(unique_id, users_name, users_email, picture)
        logger.info(f"Created new user {users_email} in the database.")

    login_user(user)

    return redirect(url_for("dashboard"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    logger.info(f"User {current_user.email} logged out.")
    return redirect(url_for("index"))


@app.route("/dashboard", methods=("GET", "POST"))
@login_required
def dashboard():
    canvas_update = sheet.last_canvas_update_time
    if sheet.canvas_is_updating:
        canvas_update = "Updating..."
    devices = sheet.reader_data.loc[
        :,
        [
            "id",
            "location",
            "alarm",
            "status",
            "alarm_status",
            "alarm_delay_min",
            "last_checked_in",
        ],
    ]

    device_info = []
    for _, device in devices.iterrows():
        alarm_color = status_colors[
            (
                -1
                if device["alarm"] not in alarm_enable_names
                else alarm_enable_names.index(device["alarm"])
            )
        ]
        status_color = status_colors[
            (
                -1
                if device["status"] not in device_status_names
                else device_status_names.index(device["status"])
            )
        ]
        warning_color = alarm_status_colors[
            (
                -1
                if device["alarm_status"] not in alarm_status_names
                else alarm_status_names.index(device["alarm_status"])
            )
        ]

        device_info.append(
            {
                "id": int(device["id"]),
                "status": device["status"],
                "alarm_power": device["alarm"],
                "alarm_enable_names": alarm_enable_names,
                "alarm_power_color": alarm_color,
                "status_color": status_color,
                "alarm_color": warning_color,
                "alarm_status": device["alarm_status"],
                "location": device["location"],
                "alarm_delay_min": device["alarm_delay_min"],
                "last_checked_in": device["last_checked_in"],
            }
        )

    try:
        if request.method == "POST":
            if request.form["label"] == "update-device":
                req_id = int(request.form.get("id"))
                req_location = request.form.get("location")
                req_alarm = request.form.get("alarm_power")
                req_delay = request.form.get("delay")

                if req_alarm:
                    device_info[req_id]["alarm_power"] = req_alarm
                    device_info[req_id]["alarm_power_color"] = status_colors[
                        (
                            -1
                            if req_alarm not in alarm_enable_names
                            else alarm_enable_names.index(req_alarm)
                        )
                    ]
                device_info[req_id]["location"] = req_location
                device_info[req_id]["alarm_delay_min"] = req_delay

                sheet.run_in_thread(
                    f=sheet.update_reader,
                    kwargs={
                        "id": req_id,
                        "location": req_location,
                        "alarm": req_alarm,
                        "alarm_delay": req_delay,
                    },
                )
                logger.info(f"Updated device {req_id} with new settings.")
                return redirect("/dashboard")
            elif request.form["label"] == "update-canvas":
                sheet.update_canvas()
                logger.info("Updating canvas")
                return redirect("/dashboard")
            elif request.form["label"] == "update-all":
                sheet.run_in_thread(f=sheet.update_all_readers)
                logger.info("Updating all readers")
                return redirect("/dashboard")

    except Exception as e:
        logger.error(e)

    return render_template(
        "dashboard.html",
        devices=device_info,
        canvas_update=canvas_update,
    )


@app.route("/setup", methods=("GET", "POST"))
@login_required
def setup():
    err = ""
    added = False

    try:
        if request.method == "POST":
            if request.form["label"] == "uidsetup" and not sheet.canvas_is_updating:
                cruzid = request.form.get("cruzid")
                overwritecheck = (
                    True if request.form.get("overwrite") == "overwrite" else False
                )
                uid = nfc.read_card()
                if not cruzid:
                    err = "Please enter a CruzID"
                    logger.warning("No CruzID provided during UID setup.")
                elif not uid:
                    err = "Card not detected, please try again"
                    logger.warning("Card not detected during UID setup.")
                else:
                    err, added = assign_uid(cruzid, overwritecheck, uid)
            elif sheet.canvas_is_updating:
                err = "Canvas is updating, please wait"
                logger.info("Canvas update in progress during UID setup.")
            else:
                err = "Invalid request"
                logger.warning("Invalid request during UID setup.")

    except Exception as e:
        logger.error(e)

    return render_template(
        "setup.html",
        err=err,
        added=added,
    )


@app.route("/identify", methods=("GET", "POST"))
@login_required
def identify():
    cruzid = ""
    uid = ""
    err = ""
    user_data = None
    accesses = []
    rooms = sheet.rooms

    try:
        if request.method == "POST":
            cruzid = ""
            if request.form["label"] == "identifyuid":
                cruzid = request.form.get("cruzid")

                if cruzid != None and cruzid != "" and cruzid != "None":
                    user_data = dict(
                        zip(
                            [
                                "type",
                                "cruzid",
                                "uid",
                                "first_name",
                                "last_name",
                            ],
                            sheet.get_user_data(cruzid=cruzid),
                        )
                    )
                    accesses = sheet.get_all_accesses(cruzid=cruzid)
                else:
                    uid = nfc.read_card()
                    user_data = dict(
                        zip(
                            [
                                "type",
                                "cruzid",
                                "uid",
                                "first_name",
                                "last_name",
                            ],
                            sheet.get_user_data(uid=uid),
                        )
                    )
                    accesses = sheet.get_all_accesses(uid=uid)

                if user_data["type"] is True:
                    user_data["type"] = "Staff"
                elif user_data["type"] is False:
                    user_data["type"] = "Student"
                else:
                    user_data["type"] = "Unknown"

    except Exception as e:
        logger.error(e)

    return render_template(
        "identify.html",
        err=err,
        user_data=user_data,
        accesses=accesses,
        rooms=rooms,
        length=0 if not rooms else len(rooms),
    )


@socketio.on("connect")
def handle_connect():
    global thread
    if thread is None or not thread.is_alive():
        logger.info("Starting background thread...")
        thread = Thread(target=background_thread)
        thread.start()


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5001, ssl_context="adhoc")
