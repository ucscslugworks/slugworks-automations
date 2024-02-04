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


from datetime import datetime
from threading import Thread
import os
import canvas
import sheet
import random


from flask import Flask, flash, render_template, request

# initialize flask app
os.chdir(os.path.dirname(os.path.realpath(__file__)))
app = Flask(__name__)
app.secret_key = os.urandom(12).hex()
sheet.get_sheet_data(limited=False)
alarm1="red"


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
    devices = sheet.reader_data.loc[:, ["id", "location", "alarm", "status", "alarm_status"]]  # Pull device data from sheet.py

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
    
    # Extract name, colour, and status attributes from devices
    device_info = []
    for _, device in devices.iterrows():
        alarm_power = device["alarm"]
        if alarm_power == "ENABLE":
            alarm_color = "#3CBC8D"
        elif alarm_power == "DISABLE":
            alarm_color = "red"
        else:
            alarm_color = ""
        device_status = device["status"]
        if device_status == "ONLINE":
            status_color = "#3CBC8D"
        elif device_status == "OFFLINE":
            status_color = "red"
        else:
            status_color = ""
        alarm_warning = device["alarm_status"]
        if alarm_warning == "OK":
            warning_color = "#3CBC8D"
        elif alarm_warning == "ALARM":
            warning_color= "red"
        elif alarm_warning == "TAGGED OUT":
            warning_color= "yellow"
        elif alarm_warning == "DISABLED":
            warning_color= "pink"
        else:
            warning_color= ""
        device_info.append({
            "name": device["id"],
            "status": device["status"],
            "alarm_power": device["alarm"],
            "alarm_power_color": alarm_color,
            "status_color": status_color,
            "alarm_color": warning_color,
            "alarm_status": device["alarm_status"],
            "location": device["location"]
            
        })

    return render_template("dashboard.html", pizerocolour1=alarm1, status_01="OK", color_01="#3CBC8D", devices=device_info)  # Pass devices to the template

if __name__ == "__main__":
    
    app.run(host="0.0.0.0", port=5001)
    
