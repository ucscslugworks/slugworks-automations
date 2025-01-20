from flask import Blueprint, jsonify, request

from src import constants
from src.server import server

# TODO: add a way (api endpoint?) to set the canvas course id

api = Blueprint("api", __name__)


def api_success(args: dict = {}):
    args["success"] = True
    return jsonify(args)


def api_fail(reason: str = ""):
    return jsonify({"success": False, "reason": reason})


# API endpoint - upload most recently scanned card uid from desk scanner
@api.route("/api/desk_uid_scan")
def desk_uid_scan():
    uid = request.args.get("uid", "", type=str)
    if server.set_desk_uid_scan(uid):
        return api_success()
    else:
        return api_fail("failed to set desk scan uid")


@api.route("/api/scan")
def scan():
    uid = request.args.get("uid", "", type=str)
    reader_id = 0  # TODO: how do we want to get the reader id? should it be passed as an arg in addition to the auth token, or do we just use the auth token to identify the reader

    result = server.scan_uid(reader_id, uid)
    if result:
        color, delay, tagout = result
        return api_success({"color": color, "delay": delay, "tagout": tagout})
    else:
        return api_fail("no color/delay available")


@api.route("/api/checkin")
def checkin():
    status = request.args.get("status", constants.ALARM_STATUS_OK, type=int)
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
