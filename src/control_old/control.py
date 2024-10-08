import datetime
import logging
import os
import time
from threading import Event, Thread

from flask import Flask, redirect, render_template, request, url_for
from flask_socketio import SocketIO

from .. import sheet
from ..desk import nfc as nfc

# Change directory to repository root
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
# Generate a random secret key for the session
app.secret_key = os.urandom(12).hex()
# Initialize SocketIO - used for sending updates to the frontend
socketio = SocketIO(app, cors_allowed_origins="*")
# create a background thread to update data
thread = None
thread_stop_event = Event()

# Get the data from the Google Sheet
sheet.get_sheet_data(limited=False)

# names and colors used by the Google Sheet
alarm_enable_names = ["ENABLE", "DISABLE"]
device_status_names = ["ONLINE", "OFFLINE"]
alarm_status_names = ["OK", "ALARM", "TAGGED OUT", "DISABLED"]

status_colors = ["#3CBC8D", "red", ""]
alarm_status_colors = ["#3CBC8D", "red", "yellow", "gray", ""]


# process for assigning a card to a user
def assign_uid(cruzid, overwrite, uid):
    """
    Assigns a card to a user in the Google Sheet

    cruzid: str - the CruzID of the user
    overwrite: bool - whether to overwrite the card if it is already assigned
    uid: str - the UID of the card

    returns: (str, bool) - an error message and whether the card was added
    """
    # true/false on whether the card was added
    added = False

    # error message to return
    carderror = ""

    if sheet.get_uid(cruzid) == uid:
        # if the specified card is already assigned to the specified user
        carderror = f"Card is already assigned to {cruzid}"
        logger.debug(carderror)
    elif sheet.get_uid(cruzid) and sheet.get_cruzid(uid) and not overwrite:
        # if the specified user already has a different card and the specified card is already assigned to a different user, and overwrite is not specified
        carderror = f"Card is already assigned to {sheet.get_cruzid(uid)}, and {cruzid} already has a card. If you would like to reassign the card to {cruzid} and replace {cruzid}'s existing card, please overwrite."
        logger.debug(carderror)
    elif sheet.get_uid(cruzid) and not overwrite:
        # if the specified user already has a different card and overwrite is not specified
        carderror = (
            f"{cruzid} already has a card, please overwrite to replace with this card"
        )
        logger.debug(carderror)
    elif sheet.get_cruzid(uid) and not overwrite:
        # if the specified card is already assigned to a different user and overwrite is not specified
        carderror = f"Card is already assigned to {sheet.get_cruzid(uid)}. If you would like to reassign the card to {cruzid}, please overwrite."
        logger.debug(carderror)
    else:
        # if the card is not assigned to this user or any other user and this user does not have a card
        # or if overwrite is specified

        # assign the card to the user (the set_uid function will handle the overwrite)
        sheet.set_uid(cruzid, uid, overwrite)

        # write the updated data to the Google Sheet
        sheet.run_in_thread(f=sheet.write_student_staff_sheets)

        carderror = f"Card added to database for {cruzid}"
        added = True
        logger.info(carderror)
    return carderror, added


UPDATE_TIMEOUT = 30  # seconds - how often to update


# function to update the data in the Google Sheet if needed
def update_data():
    if (
        not sheet.last_update_time  # never updated
        or sheet.last_canvas_update_time
        > sheet.last_update_time  # canvas updated since last data update
        or datetime.datetime.now() - sheet.last_update_time
        > datetime.timedelta(
            0, UPDATE_TIMEOUT, 0, 0, 0, 0, 0
        )  # time since last update is greater than timeout
    ):
        # update from sheet
        logger.info("Getting sheet data...")
        sheet.get_sheet_data()

        # clear timestamps (saved for debouncing)
        nfc.clear_timestamps()


# background thread to update data
def background_thread():
    # run until the stop event is set
    while not thread_stop_event.is_set():
        try:
            # call the update function
            logger.debug("Background thread updating data...")
            update_data()
            socketio.emit("update", {"message": "Data updated"})
            logger.info("Data updated and event emitted.")
            time.sleep(UPDATE_TIMEOUT / 3)  # wait for the timeout
        except Exception as e:
            logger.error(f"Error during background update: {e}")


# route for the main page
@app.route("/")
def index():
    return redirect(url_for("dashboard"))


# route for the dashboard
@app.route("/dashboard", methods=("GET", "POST"))
def dashboard():
    # check if the canvas is updating
    canvas_update = sheet.last_canvas_update_time
    if sheet.canvas_is_updating:
        canvas_update = "Updating..."

    # list of readers
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

    devices_info = []
    for _, device in devices.iterrows():
        # get the colors for the alarm (enable/disable), status (online/offline), and alarm status (triggered, tagged out, etc.)
        alarm_color = status_colors[
            (
                -1  # no color
                if device["alarm"]
                not in alarm_enable_names  # if the alarm is not in the list of alarm names
                else alarm_enable_names.index(
                    device["alarm"]
                )  # get the index of the alarm name
            )
        ]
        status_color = status_colors[
            (
                -1  # no color
                if device["status"]
                not in device_status_names  # if the status is not in the list of status names
                else device_status_names.index(
                    device["status"]
                )  # get the index of the status name
            )
        ]
        warning_color = alarm_status_colors[
            (
                -1  # no color
                if device["alarm_status"]
                not in alarm_status_names  # if the alarm status is not in the list of alarm status names
                else alarm_status_names.index(
                    device["alarm_status"]
                )  # get the index of the alarm status name
            )
        ]

        # add the device information to the list
        devices_info.append(
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
        # check if the request is a POST request - an update button was pressed
        if request.method == "POST":
            # check the label of the button that was pressed
            if request.form["label"] == "update-device":  # update device settings
                req_id = int(request.form.get("id"))  # get the ID of the device
                req_location = request.form.get(
                    "location"
                )  # get the new location of the device
                req_alarm = request.form.get(
                    "alarm_power"
                )  # get the new alarm power (enable/disable) of the device
                req_delay = request.form.get(
                    "delay"
                )  # get the new alarm delay time of the device

                # if alarm power was changed
                if req_alarm:
                    # save the new alarm power & color
                    devices_info[req_id]["alarm_power"] = req_alarm
                    devices_info[req_id]["alarm_power_color"] = status_colors[
                        (
                            -1
                            if req_alarm not in alarm_enable_names
                            else alarm_enable_names.index(req_alarm)
                        )
                    ]

                # save other settings
                devices_info[req_id]["location"] = req_location
                devices_info[req_id]["alarm_delay_min"] = req_delay

                # update the device in the Google Sheet (in the background)
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
                # return to the dashboard - redirect produces a GET request so a reload by the user doesn't resubmit the POST request
                return redirect("/dashboard")
            elif request.form["label"] == "update-canvas":  # start canvas update
                sheet.update_canvas()  # update the canvas
                logger.info("Updating canvas")
                return redirect("/dashboard")
            elif request.form["label"] == "update-all":  # update all readers
                sheet.run_in_thread(f=sheet.update_all_readers)  # update all readers
                logger.info("Updating all readers")
                return redirect("/dashboard")

    except Exception as e:
        logger.error(e)

    # render the dashboard template with the device information and canvas update status
    return render_template(
        "dashboard.html",
        devices=devices_info,
        canvas_update=canvas_update,
    )


# route for the setup page
@app.route("/setup", methods=("GET", "POST"))
def setup():
    # error message to display
    err = ""
    # whether the card was added
    added = False

    try:
        # check if the request is a POST request - the setup button was pressed
        if request.method == "POST":
            # check the label of the button that was pressed and if the canvas is updating
            # the only possible request is to assign a card to a user
            if request.form["label"] == "uidsetup" and not sheet.canvas_is_updating:
                # get the specified CruzID
                cruzid = request.form.get("cruzid")
                # whether to overwrite the card if it is already assigned (checkbox)
                overwritecheck = (
                    True if request.form.get("overwrite") == "overwrite" else False
                )
                # get the UID of the card - read from the NFC reader
                uid = nfc.read_card()

                # if the CruzID is not provided or the card is not detected, display an error message
                if not cruzid:
                    err = "Please enter a CruzID"
                    logger.warning("No CruzID provided during UID setup.")
                elif not uid:
                    err = "Card not detected, please try again"
                    logger.warning("Card not detected during UID setup.")
                else:
                    # assign the card to the user (or get an error back)
                    err, added = assign_uid(cruzid, overwritecheck, uid)
            elif sheet.canvas_is_updating:
                # if the canvas is updating, display an error message
                err = "Canvas is updating, please wait"
                logger.info("Canvas update in progress during UID setup.")
            else:
                # if the request is invalid, display an error message
                err = "Invalid request"
                logger.warning("Invalid request during UID setup.")

    except Exception as e:
        logger.error(e)

    # display the setup template with the error message and whether the card was added
    return render_template(
        "setup.html",
        err=err,
        added=added,
    )


# route for the identify page
@app.route("/identify", methods=("GET", "POST"))
def identify():
    cruzid = ""  # CruzID of the user
    uid = ""  # UID of the card
    err = ""  # error message
    user_data = None  # list for user data - type, cruzid, uid, first name, last name
    accesses = []  # list for accesses - true/false
    rooms = sheet.rooms  # list of room names

    try:
        # check if the request is a POST request - the identify button was pressed
        if request.method == "POST":
            # clear the cruzid (this will be shown on the page whether the identify succeeds or not)
            cruzid = ""

            # check the label of the button that was pressed - the only possible value should be "identifyuid"
            if request.form["label"] == "identifyuid":
                # get the CruzID from the form
                cruzid = request.form.get("cruzid")

                # if the CruzID is provided, look up the user data and accesses from the sheet
                if cruzid != None and cruzid != "" and cruzid != "None":
                    user_data = dict(
                        zip(
                            [
                                "is_staff",
                                "cruzid",
                                "uid",
                                "first_name",
                                "last_name",
                            ],
                            sheet.get_user_data(cruzid=cruzid),
                        )
                    )
                    accesses = sheet.get_all_accesses(cruzid=cruzid)
                else:  # if the CruzID is not provided, read the card from the NFC reader
                    uid = nfc.read_card()
                    # look up the user data and accesses from the sheet
                    user_data = dict(
                        zip(
                            [
                                "is_staff",
                                "cruzid",
                                "uid",
                                "first_name",
                                "last_name",
                            ],
                            sheet.get_user_data(uid=uid),
                        )
                    )
                    accesses = sheet.get_all_accesses(uid=uid)

                # depending on the is_staff value, set the type to Staff or Student
                if user_data["is_staff"] is True:
                    user_data["type"] = "Staff"
                elif user_data["is_staff"] is False:
                    user_data["type"] = "Student"
                else:
                    user_data["type"] = "Unknown"

    except Exception as e:
        logger.error(e)

    # render the identify template with the error message, user data, accesses, room names, and room count
    return render_template(
        "identify.html",
        err=err,
        user_data=user_data,
        accesses=accesses,
        rooms=rooms,
        length=0 if not rooms else len(rooms),
    )


# start background thread when the site is loaded
@socketio.on("connect")
def handle_connect():
    global thread
    # start the background thread if it is not already running
    if thread is None or not thread.is_alive():
        logger.info("Starting background thread...")
        thread = Thread(target=background_thread)
        thread.start()


if __name__ == "__main__":
    # run the app on port 5001
    socketio.run(app, host="0.0.0.0", port=5001, ssl_context="adhoc")
