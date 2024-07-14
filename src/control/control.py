import datetime
import json
import logging
import os
import sqlite3
import time
from threading import Event, Thread

import requests
from flask import Flask, redirect, render_template, request, url_for
from flask_socketio import SocketIO, emit

from ..nfc import nfc_fake as nfc

# from ..nfc import nfc_control as nfc

from .. import sheet

# Change directory to current file location
path = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
os.chdir(path)

# Create a new directory for logs if it doesn't exist
if not os.path.exists(path + "/logs/control"):
    os.makedirs(path + "/logs/control")

# create new logger with all levels
logger = logging.getLogger("root")
logger.setLevel(logging.DEBUG)

# create file handler which logs debug messages (and above - everything)
fh = logging.FileHandler(f"logs/control/{str(datetime.datetime.now())}.log")
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
    if (
        not sheet.last_update_time
        or sheet.last_canvas_update_time > sheet.last_update_time
        or datetime.datetime.now() - sheet.last_update_time
        > datetime.timedelta(0, CHECKIN_TIMEOUT, 0, 0, 0, 0, 0)
    ):
        logger.info("Getting sheet data...")
        sheet.get_sheet_data()
        nfc.clear_timestamps()


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
    return redirect(url_for("dashboard"))


@app.route("/dashboard", methods=("GET", "POST"))
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
