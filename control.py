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

from flask import Flask, flash, redirect, render_template, request, url_for

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

def staff_or_student(cruzid, overwritecheck, uid ):
    if sheet.is_staff(cruzid=cruzid) or sheet.is_staff(uid="uid"):
        return assign_staff_uid(cruzid, uid, overwritecheck)
    elif sheet.student_exists(cruzid=cruzid) or sheet.student_exists(uid="uid"):
        return assign_student_uid(cruzid, overwritecheck, uid)
    else:
        carderror="CruzID not in database, please add user to Canvas first, then update database"
        return carderror, False


def assign_student_uid(cruzid, overwritecheck, uid):  # set uid
    added = False
    carderror = ""
    if sheet.is_staff(cruzid=cruzid):
        carderror = f"{cruzid} is a staff member, please use a student CruzID"
    elif not sheet.student_exists(cruzid=cruzid):
        carderror = f"CruzID {cruzid} not in database, please add student to Canvas first, then update database"
    elif sheet.get_uid(cruzid) == uid:
        carderror = f"Card is already assigned to {cruzid}"
    elif sheet.get_uid(cruzid) and not overwritecheck:
        carderror = (
            f"{cruzid} already has a card, please overwrite to replace with this card"
        )
    elif sheet.get_cruzid(uid) and not overwritecheck:
        carderror = f"Card is already assigned to {sheet.get_cruzid(uid)}. If you would like to reassign the card to {cruzid}, please overwrite."
    else:
        sheet.set_uid(cruzid, uid, overwritecheck)
        sheet.run_in_thread(f=sheet.write_student_staff_sheets)
        carderror = f"Card added to database for {cruzid}"
        added = True

    return carderror, added


# If they are not staff, but they are a student complain
# if they are not staff && not student check if Firstname Lastname is provided if not complain
# ELSE: (at this point either cruzid is alrdy staff or they are neither staff nor student and have provided a name)
# do standard cruzid && uid checks
# if all checks pass, add to staff sheet
# IDEAS:
# add a list of staff with a remove button
def assign_staff_uid(cruzid, first, last, uid, overwrite):  # set
    print("assigning staff UID", cruzid, overwrite, uid)
    added = False
    carderror = ""
    if not sheet.is_staff(cruzid=cruzid) and sheet.student_exists(cruzid=cruzid):
        carderror = "CruzID is a student, please mark as a staff member in Canvas and perform a Canvas update"
    elif (
        not sheet.is_staff(cruzid=cruzid)
        and not sheet.student_exists(cruzid=cruzid)
        and (not first or not last)
    ):
        carderror = "Please provide a first and last name"
    elif (
        not sheet.is_staff(cruzid=cruzid)
        and not sheet.student_exists(cruzid=cruzid)
        and first
        and last
    ) or sheet.is_staff(cruzid=cruzid):
        if sheet.get_uid(cruzid) == uid:
            carderror = f"Card is already assigned to {cruzid}"
        elif sheet.get_uid(cruzid) and not overwrite:
            carderror = f"{cruzid} already has a card, please overwrite to replace with this card"
        elif sheet.get_cruzid(uid) and not overwrite:
            carderror = f"Card is already assigned to {sheet.get_cruzid(uid)}. If you would like to reassign the card to {cruzid}, please overwrite."
        else:
            # if not sheet.is_staff(cruzid):
            #     sheet.new_staff(first, last, cruzid, uid)
            #     carderror = f"New staff member {first} {last} added to database with CruzID {cruzid}"
            # else:
            sheet.set_uid(cruzid, uid, overwrite)
            carderror = f"Card added to database for {cruzid}"
            added = True
            sheet.run_in_thread(f=sheet.write_student_staff_sheets)
    return carderror, added

def find_owner(uid):
    info = sheet.get_user_data(uid)
    return info

    # print(0)
    # if sheet.is_staff(cruzid=cruzid):
    #     print(1)
    #     carderror = "Staff member, please use a student CruzID"
    # elif not sheet.student_exists(cruzid=cruzid):
    #     print(2)
    #     carderror = "CruzID not in database, please add student to Canvas first, then update database"
    # elif sheet.get_uid(cruzid) == uid:
    #     print(3)
    #     carderror = f"Card is already assigned to {cruzid}"
    # elif sheet.get_uid(cruzid) is not None and not overwritecheck:
    #     print(4)
    #     carderror = (
    #         f"{cruzid} already has a card, please overwrite to replace with this card"
    #     )
    # elif sheet.get_cruzid(uid) is not None and not overwritecheck:
    #     print(5)
    #     carderror = f"Card is already assigned to {sheet.get_cruzid(uid)}. If you would like to reassign the card to {cruzid}, please overwrite."
    # else:
    #     print(6)
    #     sheet.set_uid(cruzid, uid, overwritecheck)
    #     print(7)
    #     # sheet.run_in_thread(f=sheet.write_student_sheet)
    #     sheet.write_student_sheet()
    #     carderror = "Card added to database"


@app.route("/", methods=("GET", "POST"))
def server():
    err = ""
    wait = False
    canvas_update = sheet.last_canvas_update_time 
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
                canvas_update = sheet.last_canvas_update_time

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
                return redirect("/")
            elif request.form["label"] == "update-canvas":
                print("im updating canvas")
                # canvas.update()
                return redirect("/")

    except Exception as e:
        print(e)

    return render_template(
        "dashboard.html", devices=device_info, canvas_update=canvas_update,
    )  # Pass devices to the template


@app.route("/card", methods=("GET", "POST"))
def card():
    err = ""
    added = False

    try:
        if request.method == "POST":
            flash("You are using POST")
            print(request.form)
            sheet.get_canvas_status_sheet()
            print("status")
            print(sheet.canvas_is_updating)
            if request.form["label"] == "uidsetup" and sheet.canvas_is_updating == False:
                print("reading UID")
                cruzid = request.form.get("cruzid")
                #sheet.last_canvas_update_time
             
                overwritecheck = (
                    True if request.form.get("overwrite") == "overwrite" else False
                )
                uid = nfc.read_card()
                print(cruzid, overwritecheck, uid)
                if not cruzid:
                    err = "Please enter a CruzID"
                elif not uid:
                    err = "Card not detected, please try again"
                else:
                    err, added = staff_or_student(cruzid, overwritecheck, uid)
                    # err = "temp"
            else:
                err = "Canvas is updating, please wait"

    except Exception as e:
        print(e)

    return render_template(
        "student.html",
        err=err,
        added=added,
    )

@app.route("/identify", methods=("GET", "POST"))
def identify():
    cruzid = ""
    uid = ""
    err = ""
    user_data = None

    try:
        if request.method == "POST":
            flash("You are using POST")
            # print(request.form)
            if request.form["label"] == "identifyuid":
                print("reading UID")
                uid = nfc.read_card()
                print(uid)
                user_data = dict(zip(["is_staff", "cruzid", "uid", "first_name", "last_name", "access1", "access2", "access3", "access4", "access5", "access6", "access7", "access8"], sheet.get_user_data(uid=uid)))
                print(user_data)
                
                # if uid:
                #     if find_owner(uid) is not None:
                #         cruzid = find_owner(uid)
                #     else:
                #         err = "User not found in the database. Please add the user to the database first."
                # else:
                #     err = "Card not detected. Please try again."

    except Exception as e:
        print(e)

    return render_template(
        "identify.html",
        # cruzid=cruzid,
        # uid=uid,
        err=err,
        user_data=user_data,

    )


# @app.route("/staff", methods=("GET", "POST"))

# # TODO:
# # If they are not staff, but they are a student complain
# # if they are not staff && not student check if Firstname Lastname is provided if not complain
# # ELSE: (at this point either cruzid is alrdy staff or they are neither staff nor student and have provided a name)
# # do standard cruzid && uid checks
# # if all checks pass, add to staff sheet
# # IDEAS:
# # add a list of staff with a remove button


# def staff():
#     err = ""
#     added = False

#     try:
#         if request.method == "POST":
#             flash("You are using POST")
#             print(request.form)
#             if request.form["label"] == "uidsetup":
#                 print("reading UID")
#                 cruzid = request.form.get("cruzid")
#                 overwritecheck = (
#                     True if request.form.get("overwrite") == "overwrite" else False
#                 )
#                 uid = nfc.read_card()
#                 print(cruzid, overwritecheck, uid)
#                 if not cruzid:
#                     err = "Please enter a CruzID"
#                 elif not uid:
#                     err = "Card not detected, please try again"
#                 else:
#                     # err = assign_uid(cruzid, overwritecheck, uid)
#                     # err = "temp"
#                     err, added = assign_staff_uid(
#                         cruzid,
#                         request.form.get("first"),
#                         request.form.get("last"),
#                         uid,
#                         overwritecheck,
#                     )

#     except Exception as e:
#         print(e)

#     return render_template("staff.html", err=err, added=added)


CANVAS_UPDATE_HOUR = 20  # 3am
CHECKIN_TIMEOUT = 30  # 30 seconds

card_id = None

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
    # sheet.get_sheet_data(limited=False)
    # sheet.check_in()
    # t = Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": 5001})
    # print(sheet.access_data)
    # while True:
    #     continue
    #     if (
    #         not sheet.last_update_date or datetime.now().date() > sheet.last_update_date
    #     ) and datetime.now().hour >= CANVAS_UPDATE_HOUR:
    #         print("Canvas update...")
    #         # canvas.update()
    #         sheet.get_sheet_data()
    #         sheet.check_in()
    #     elif (
    #         not sheet.last_checkin_time
    #         or datetime.now() - sheet.last_checkin_time
    #         > timedelta(0, CHECKIN_TIMEOUT, 0, 0, 0, 0, 0)
    #     ):
    #         print("Checking in...")
    #         sheet.check_in()
    #     # time.sleep(60)
    #     print("Hold a tag near the reader")
    #     card_id = nfc.read_card()
    #     print(card_id)
    #     if card_id:
    #         response = sheet.scan_uid(card_id)
    #         if not response:
    #             print("error - card not in database or something else")
    #             pass
    #         else:
    #             color, timeout = response
    #             print(color, timeout)
    #     else:
    #         print("error - scanned too soon or not scanned")
