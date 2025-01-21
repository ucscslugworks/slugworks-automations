from flask import Blueprint, render_template

ui = Blueprint("ui", __name__)

# TODO: need to set up the ui pages


# main dashboard page
@ui.route("/")
def dashboard():
    return render_template("dashboard.html")


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
