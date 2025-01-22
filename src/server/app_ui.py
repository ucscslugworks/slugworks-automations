from flask import Blueprint, render_template, request, redirect, url_for
from src import constants, log
from src.server import server
from datetime import datetime

ui = Blueprint("ui", __name__)

# TODO: need to set up the ui pages
logger = log.setup_logs("flask")


# main dashboard page
@ui.route("/", methods=["GET", "POST"])
def dashboard():
    if request.method == "POST":
        rid = request.form.get(f"rid", -1)
        enable = int(request.form.get(f"enable", None))
        loc = str(request.form.get(f"loc", None))
        delay = request.form.get(f"delay", None)
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
def users():
    cruzid = None
    uid = None
    if request.method == "POST":
        cruzid = request.form.get(f"cruzid", None)
        uid = request.form.get(f"uid", None)
        if cruzid is not None:
            logger.info(f"Searching for {cruzid}")
            uid = server.get_uid(cruzid)
        elif uid is not None:
            logger.info(f"Searching for {uid}")
            cruzid = server.get_cruzid(uid)
    return render_template("users.html", cruzid=cruzid, uid=uid)


# config page
@ui.route("/config")
def config():
    return render_template("config.html")


# logs page
@ui.route("/logs")
def logs():
    return render_template("logs.html")
