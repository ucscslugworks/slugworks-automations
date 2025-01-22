from flask import Blueprint, render_template, request
from src import constants
from src.server import server

ui = Blueprint("ui", __name__)

# TODO: need to set up the ui pages


# main dashboard page
@ui.route("/")
def dashboard():
    readers = server.get_readers()
    for i, r in enumerate(readers):
        rid, online, loc, enable, delay, status, last_seen = r
        readers[i] = {
            "id": rid,
            "online": online,
            "loc": loc,
            "enable": enable,
            "delay": delay,
            "status": status,
            "last_seen": last_seen,
        }
    return render_template("dashboard.html", readers=readers)


# users page
@ui.route("/users")
def users():
    return render_template("users.html")


# config page
@ui.route("/config")
def config():
    return render_template("config.html")


# logs page
@ui.route("/logs")
def logs():
    return render_template("logs.html")
