import os

from flask import Flask, jsonify, redirect, render_template, request, url_for

from src import log
from src.server import server

# Change directory to repository root
path = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
os.chdir(path)

# Create a new logger for the flask module
logger = log.setup_logs("flask", log.INFO)

# Initialize Flask app
app = Flask(__name__)
# Generate a random secret key for the session
app.secret_key = os.urandom(12).hex()


# main dashboard page
@app.route("/")
def dashboard():
    return "dashboard"


# new user page
@app.route("/new")
def new():
    return "new"


# edit user page
@app.route("/edit")
def edit():
    return "edit"


# identify user page
@app.route("/identify")
def identify():
    return "identify"


def api_success(args: dict = {}):
    return jsonify({"success": True} + args)


def api_fail(reason: str = ""):
    return jsonify({"success": False, "reason": reason})


# API page - upload most recently scanned card uid from desk scanner
@app.route("/api/desk_uid_scan")
def desk_uid_scan():
    uid = request.args.get("uid", "", type=str)
    if server.set_desk_uid_scan(uid):
        return api_success()
    else:
        return api_fail("failed to set desk scan uid")


@app.route("/api/tagout")
def tagout():
    uid = server.get_tagout()
    if uid is not False:
        return api_success({"uid": uid})
    else:
        return api_fail("failed to get tagout uid")


@app.route("/api/scan")
def scan():
    uid = request.args.get("uid", "", type=str)
    reader_id = 0  # TODO: how do we want to get the reader id? should it be passed as an arg in addition to the auth token, or do we just use the auth token to identify the reader

    result = server.scan_uid(reader_id, uid)
    if result:
        color, delay = result
        return api_success({"color": color, "delay": delay})
    else:
        return api_fail("no color/delay available")


@app.route("/api/checkin")
def checkin():
    status = request.args.get("status", server.ALARM_STATUS_OK, type=int)
    reader_id = 0

    if not server.check_in(reader_id, status):
        return api_fail("check-in failed")

    result = server.get_reader_settings(reader_id)

    if not result:
        return api_fail("get_reader_settings failed")

    _, alarm_enable, alarm_delay_min = result

    return api_success(
        {
            "alarm_enable": alarm_enable,
            "alarm_delay_min": alarm_delay_min,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
