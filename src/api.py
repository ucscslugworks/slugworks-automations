import logging

import requests


class DummyObject(object):
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


SERVER_IP = "http://localhost:5001"
base_url = f"{SERVER_IP}/api"

logger = DummyObject()


def set_logger(module_logger: logging.Logger):
    global logger
    logger = module_logger


def handle_response(response: requests.Response):
    try:
        response_json = response.json()
        success = response_json["success"]
        return (
            success,
            response_json,
        )
    except Exception as e:
        logger.error(f"api - handle_response - {e}")
    return (False, {})


def desk_uid_scan(uid: str):
    try:
        response = requests.get(f"{base_url}/desk_uid_scan", params={"uid": uid})
        if response.status_code == 200:
            return handle_response(response)
    except Exception as e:
        logger.error(f"api - desk_uid_scan - {e}")
    return (False, {})


def tagout():
    try:
        response = requests.get(f"{base_url}/tagout")
        if response.status_code == 200:
            return handle_response(response)
    except Exception as e:
        logger.error(f"api - tagout - {e}")
    return (False, {})


def scan(uid: str):
    try:
        response = requests.get(f"{base_url}/scan", params={"uid": uid})
        if response.status_code == 200:
            return handle_response(response)
    except Exception as e:
        logger.error(f"api - scan - {e}")
    return (False, {})


def checkin(status: int):
    try:
        response = requests.get(f"{base_url}/checkin", params={"status": status})
        if response.status_code == 200:
            return handle_response(response)
    except Exception as e:
        logger.error(f"api - checkin - {e}")
    return (False, {})
