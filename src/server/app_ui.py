from datetime import datetime

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import login_required

from src import constants, log
from src.server import server

ui = Blueprint("ui", __name__)

# TODO: need to set up the ui pages
logger = log.setup_logs("flask")


@ui.route("/")
def home():
    return render_template("home.html")


# main dashboard page
@ui.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    if request.method == "POST":
        rid = str(request.form.get(f"rid", ""))
        if not rid.isnumeric():
            return redirect(url_for("ui.dashboard"))
        else:
            rid = int(rid)

        enable = str(request.form.get(f"enable", ""))
        if enable:
            enable = True
        else:
            enable = False

        loc = str(request.form.get(f"loc", ""))
        if not loc:
            loc = None

        delay = str(request.form.get(f"delay", ""))
        if delay and delay.isnumeric():
            delay = int(delay)
        else:
            delay = None

        server.set_reader_settings(rid, loc, enable, delay)
        logger.info(f"{rid}, {loc}, {enable}, {delay}")
        return redirect(url_for("ui.dashboard"))

    readers = server.get_readers()
    c_status, c_time = server.get_canvas_status()
    canvas = {
        "status": "",
        "time": "",
    }
    if c_time == constants.NEVER:
        canvas["time"] = "Never"
    else:
        canvas["time"] = datetime.fromtimestamp(c_time).strftime("%Y-%m-%d %H:%M")

    if c_status == constants.CANVAS_OK:
        canvas["status"] = "OK"
    elif c_status == constants.CANVAS_UPDATING:
        canvas["status"] = "Updating"
    elif c_status == constants.CANVAS_PENDING:
        canvas["status"] = "Pending Update"

    for i, r in enumerate(readers):
        rid, online, loc, enable, delay, status, last_seen = r
        readers[i] = {
            "id": rid,
            "online": online,
            "loc": loc,
            "enable": enable,
            "delay": delay,
            "status": status,
            "last_seen": datetime.fromtimestamp(last_seen).strftime("%Y-%m-%d %H:%M"),
        }

    return render_template("dashboard.html", readers=readers, canvas=canvas)


# users page
@ui.route("/users", methods=["GET", "POST"])
@login_required
def users():
    cruzid = None
    uid = None
    data = {"type": "", "cruzid": "", "firstname": "", "lastname": "", "uid": ""}
    rooms = {}

    if request.method == "POST":
        logger.info(f"{request.form}")
        cruzid = request.form.get(f"cruzid", None)
        uid = request.form.get(f"uid", None)
        user_data = {}
        if cruzid is not None:
            logger.info(f"Searching for {cruzid}")
            user_data = server.get_user_data(cruzid=cruzid)
        elif uid is not None:
            logger.info(f"Searching for {uid}")
            user_data = server.get_user_data(uid=uid)

        logger.info(f"User data: {user_data}")

        if type(user_data) is dict:
            for k in user_data:
                if k not in data:
                    if user_data[k] == constants.ACCESS_YES:
                        rooms[k] = "Yes"
                    elif user_data[k] == constants.ACCESS_NO:
                        rooms[k] = "No"
                    elif user_data[k] == constants.ACCESS_YES_OVERRIDE:
                        rooms[k] = "Yes (overridden)"
                    elif user_data[k] == constants.ACCESS_NO_OVERRIDE:
                        rooms[k] = "No (overridden)"
                    else:
                        rooms[k] = "Unknown"

            data = user_data
    return render_template("users.html", data=data, rooms=rooms)


# config page
@ui.route("/config")
@login_required
def config():
    return render_template("config.html")


# logs page
@ui.route("/logs")
@login_required
def logs():
    return render_template("logs.html")
