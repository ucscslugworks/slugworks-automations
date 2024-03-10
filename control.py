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
import random
from datetime import datetime
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

    try:
        if request.method == "POST":
            flash("You are using POST")
            if request.form["label"] == "update-device":
                request_data = request.form.get("device.name")

                print("update this data")
                location = request.form.get("location")
                alarm = request.form.get("alarm_power")
                delay = request.form.get("delay")
                print(location, alarm, delay, "hi")

    except Exception as e:
        print(e)

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
                "name": device["id"],
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
