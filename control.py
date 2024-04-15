import json
import os
import sqlite3
from datetime import datetime, timedelta

import requests
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from oauthlib.oauth2 import WebApplicationClient

# import control_nfc as nfc
import fake_nfc as nfc
import sheet
from db import init_db_command
from user import User

# Configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", sheet.creds.client_id)
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", sheet.creds.client_secret)
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


# initialize flask app
os.chdir(os.path.dirname(os.path.realpath(__file__)))
app = Flask(__name__)
app.secret_key = os.urandom(12).hex()

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
except sqlite3.OperationalError:
    # Assume it's already been created
    pass

# OAuth 2 client setup
client = WebApplicationClient(GOOGLE_CLIENT_ID)


# Flask-Login helper to retrieve a user from our db
@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)


@login_manager.unauthorized_handler
def unauthorized():
    return redirect("/login")


def assign_uid(cruzid, overwrite, uid):
    added = False
    carderror = ""
    if sheet.get_uid(cruzid) == uid:
        carderror = f"Card is already assigned to {cruzid}"
    elif sheet.get_uid(cruzid) and sheet.get_cruzid(uid) and not overwrite:
        carderror = f"Card is already assigned to {sheet.get_cruzid(uid)}, and {cruzid} already has a card. If you would like to reassign the card to {cruzid} and replace {cruzid}'s existing card, please overwrite."
    elif sheet.get_uid(cruzid) and not overwrite:
        carderror = (
            f"{cruzid} already has a card, please overwrite to replace with this card"
        )
    elif sheet.get_cruzid(uid) and not overwrite:
        carderror = f"Card is already assigned to {sheet.get_cruzid(uid)}. If you would like to reassign the card to {cruzid}, please overwrite."
    else:
        sheet.set_uid(cruzid, uid, overwrite)
        sheet.run_in_thread(f=sheet.write_student_staff_sheets)
        carderror = f"Card added to database for {cruzid}"
        added = True
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
        print("Getting sheet data...")
        sheet.get_sheet_data()


@app.route("/")
def index():
    if current_user.is_authenticated:
        return (
            "<p>Hello, you're logged in as {}! Email: {}</p>"
            "<a class='button' href='/dashboard'>Dashboard</a><br>"
            '<a class="button" href="/logout">Logout</a>'.format(
                current_user.name, current_user.email
            )
        )
    else:
        return '<a class="button" href="/login">Google Login</a>'


def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL).json()


@app.route("/login")
def login():
    # Find out what URL to hit for Google login
    google_provider_cfg = get_google_provider_cfg()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]

    # Use library to construct the request for Google login and provide
    # scopes that let you retrieve user's profile from Google
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=request.base_url + "/callback",
        scope=["openid", "email", "profile"],
    )
    return redirect(request_uri)


@app.route("/login/callback")
def callback():
    # Get authorization code Google sent back to you
    code = request.args.get("code")
    # Find out what URL to hit to get tokens that allow you to ask for
    # things on behalf of a user
    google_provider_cfg = get_google_provider_cfg()
    token_endpoint = google_provider_cfg["token_endpoint"]

    # Prepare and send a request to get tokens! Yay tokens!
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

    # Parse the tokens!
    client.parse_request_body_response(json.dumps(token_response.json()))

    # Now that you have tokens (yay) let's find and hit the URL
    # from Google that gives you the user's profile information,
    # including their Google profile image and email
    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)

    # You want to make sure their email is verified.
    # The user authenticated with Google, authorized your
    # app, and now you've verified their email through Google!
    if userinfo_response.json().get("email_verified"):
        unique_id = userinfo_response.json()["sub"]
        users_email = userinfo_response.json()["email"]
        picture = userinfo_response.json()["picture"]
        users_name = userinfo_response.json()["given_name"]
    else:
        return "User email not available or not verified by Google.", 400

    # Create a user in your db with the information provided
    # by Google
    user = User(id_=unique_id, name=users_name, email=users_email, profile_pic=picture)

    # Doesn't exist? Add it to the database.
    if not User.get(unique_id):
        User.create(unique_id, users_name, users_email, picture)

    # Begin user session by logging the user in
    login_user(user)

    # Send user back to homepage
    return redirect(url_for("dashboard"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/dashboard", methods=("GET", "POST"))
@login_required
def dashboard():
    update_data()
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
    ]  # Pull device data from sheet.py

    # Extract name, colour, and status attributes from devices
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
            # flash("You are using POST")

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
                return redirect("/dashboard")
            elif request.form["label"] == "update-canvas":
                sheet.update_canvas()
                print("Updating canvas")
                return redirect("/dashboard")
            elif request.form["label"] == "update-all":
                sheet.run_in_thread(f=sheet.update_all_readers)
                return redirect("/dashboard")

    except Exception as e:
        print(e)

    return render_template(
        "dashboard.html",
        devices=device_info,
        canvas_update=canvas_update,
    )  # Pass devices to the template


@app.route("/setup", methods=("GET", "POST"))
@login_required
def setup():
    update_data()
    err = ""
    added = False

    try:
        if request.method == "POST":
            # flash("You are using POST")
            if request.form["label"] == "uidsetup" and not sheet.canvas_is_updating:
                cruzid = request.form.get("cruzid")
                overwritecheck = (
                    True if request.form.get("overwrite") == "overwrite" else False
                )
                uid = nfc.read_card()
                if not cruzid:
                    err = "Please enter a CruzID"
                elif not uid:
                    err = "Card not detected, please try again"
                else:
                    err, added = assign_uid(cruzid, overwritecheck, uid)
            elif sheet.canvas_is_updating:
                err = "Canvas is updating, please wait"
            else:
                err = "Invalid request"

    except Exception as e:
        print(e)

    return render_template(
        "setup.html",
        err=err,
        added=added,
    )


@app.route("/identify", methods=("GET", "POST"))
@login_required
def identify():
    update_data()
    cruzid = ""
    uid = ""
    err = ""
    user_data = None
    accesses = []
    rooms = sheet.rooms

    try:
        if request.method == "POST":
            cruzid = ""
            # flash("You are using POST")
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
        print(e)

    return render_template(
        "identify.html",
        err=err,
        user_data=user_data,
        accesses=accesses,
        rooms=rooms,
        length=0 if not rooms else len(rooms),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, ssl_context="adhoc")
