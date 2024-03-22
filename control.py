# https://www.digitalocean.com/community/tutorials/how-to-make-a-web-application-using-flask-in-python-3
# force update button for pi5 funcheck
# force update button for pizero funcheck
# button to update both funcheck
# status of reader funcheck
# status of last update funcheck
# format student id  funcheck
# enter cruzid
# prompt button to start reader
# show warning if card already exists and if they want to overwrite funkcheck
# show a warning if the cruzid is not in the database funkcheck
# once button is pressed, show a message that the card is being written funkcheck
# write to the sheet funcheck
# show a message that the card has been written and added to sheet funkcheck


import os
import time
from datetime import datetime, timedelta
from threading import Thread

from flask import Flask, flash, render_template, request

import canvas

# import control_nfc as nfc
import fake_nfc as nfc
import sheet

# initialize flask app
os.chdir(os.path.dirname(os.path.realpath(__file__)))
app = Flask(__name__)
app.secret_key = os.urandom(12).hex()
sheet.get_sheet_data(limited=False)
alarm_enable_names = ["ENABLE", "DISABLE"]
device_status_names = ["ONLINE", "OFFLINE"]
status_colors = ["#3CBC8D", "red", ""]
alarm_status_names = ["OK", "ALARM", "TAGGED OUT", "DISABLED"]
alarm_status_colors = ["#3CBC8D", "red", "yellow", "gray"]


# TODO: this just needs canvas.update() and then sheet.check_in(alarm_status=False)
def updateme():  # updates the pi5
    print("Updating")
    # if pi5update < datetime.now()
    # if time > 3am and time < 5am
    # update the pi5 with canvas
    canvas.update()

    # update the pizero
    pi5update = datetime.now()
    print("Updated")


# TODO: use sheet.update_all_readers() to set all readers to need updating
def updatemyfriends():  # updates the pizero
    print("Updating")
    pizeroupdate = datetime.now()
    # update the pizero
    print("Updated")


# TODO: just call updateme() then updatemyfriends()
def updateall():  # updates both
    print("Updating")
    pitupdateall = datetime.now()
    canvas.update()
    # update the pizero
    print("Updated")


def status():  # status of reader
    print("Status")
    # status of reader


def formatid(cruzid, overwritecheck):  # format student id
    print("Formatting")
    carderror = uidread(cruzid, overwritecheck)
    sheet.write_student_sheet()

    return carderror

    # format student id


def uidread(cruzid, overwritecheck):  # set uid
    print("reading UID", cruzid, overwritecheck)
    # read uid function

    uid = "73B104FF"

    # if cruzid does not exist
    # add student to canvas
    # elif uid exists
    # if uid belongs to this cruzid
    # do you want to overwrite?
    # else
    # another student already has this uid
    # else
    # set uid to cruzid

    if sheet.student_exists(uid=uid):
        if overwritecheck == None:
            carderror = "Card already exists would you like to overwrite?"
        else:
            sheet.set_uid(cruzid, uid, overwritecheck)
            success = "Card added to database"
    elif not sheet.student_exists(cruzid=cruzid):
        carderror = "Cruzid not in database please add student to canvas first, and update database"
        print(cruzid)
    elif not sheet.get_uid(cruzid):
        # carderror = "success"
        sheet.set_uid(cruzid, uid, overwritecheck)
        success = "Card added to database"
    else:
        if overwritecheck == None:
            carderror = "Student already has an id would you like to overwrite?"
        else:
            sheet.set_uid(cruzid, uid, overwritecheck)
            success = "Card added to database"

    return carderror


@app.route("/", methods=("GET", "POST"))
def server():
    err = ""
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
    # print(devices, sheet.this_reader)

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
                "id": device["id"],
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
            flash("You are using POST")
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
                # sheet.run_in_thread(f=sheet.update_reader, kwargs={"id": req_id})

    except Exception as e:
        print(e)

    return render_template(
        "dashboard.html", devices=device_info
    )  # Pass devices to the template


@app.route("/student", methods=("GET", "POST"))
def student():
    err = ""

    try:
        if request.method == "POST":
            flash("You are using POST")
            if request.form["label"] == "uidsetup":
                print("reading UID")
                cruzid = request.form.get("cruzid")
                overwritecheck = request.form.get("overwrite")
                print(cruzid, overwritecheck)

                err = formatid(cruzid, overwritecheck)

    except Exception as e:
        print(e)

    return render_template("student.html", err=err)


CANVAS_UPDATE_HOUR = 20  # 3am
CHECKIN_TIMEOUT = 30  # 30 seconds

card_id = None

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
    # sheet.get_sheet_data(limited=False)
    # sheet.check_in()
    # t = Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": 5001})
    # print(sheet.access_data)
    while True:
        continue
        if (
            not sheet.last_update_date or datetime.now().date() > sheet.last_update_date
        ) and datetime.now().hour >= CANVAS_UPDATE_HOUR:
            print("Canvas update...")
            # canvas.update()
            sheet.get_sheet_data()
            sheet.check_in()
        elif (
            not sheet.last_checkin_time
            or datetime.now() - sheet.last_checkin_time
            > timedelta(0, CHECKIN_TIMEOUT, 0, 0, 0, 0, 0)
        ):
            print("Checking in...")
            sheet.check_in()
        # time.sleep(60)
        print("Hold a tag near the reader")
        card_id = nfc.read_card()
        print(card_id)
        if card_id:
            response = sheet.scan_uid(card_id)
            if not response:
                print("error - card not in database or something else")
                pass
            else:
                color, timeout = response
                print(color, timeout)
        else:
            print("error - scanned too soon or not scanned")

