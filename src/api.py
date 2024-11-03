import logging

import requests

from src.log import setup_logs

SERVER_IP = "localhost"
base_url = f"{SERVER_IP}/api"

logger = setup_logs("api", logging.INFO)


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
    return (False, dict())


def desk_uid_scan(uid: str):
    try:
        response = requests.get(f"{base_url}/desk_uid_scan", params={"uid": uid})
        if response.status_code == 200:
            return handle_response(response)
    except Exception as e:
        logger.error(f"api - desk_uid_scan - {e}")
    return (False, dict())


def tagout():
    try:
        response = requests.get(f"{base_url}/tagout")
        if response.status_code == 200:
            return handle_response(response)
    except Exception as e:
        logger.error(f"api - tagout - {e}")
    return (False, dict())


def scan(uid: str):
    try:
        response = requests.get(f"{base_url}/scan", params={"uid": uid})
        if response.status_code == 200:
            return handle_response(response)
    except Exception as e:
        logger.error(f"api - scan - {e}")
    return (False, dict())


def checkin(status: int):
    try:
        response = requests.get(f"{base_url}/checkin", params={"status": status})
        if response.status_code == 200:
            return handle_response(response)
    except Exception as e:
        logger.error(f"api - checkin - {e}")
    return (False, dict())
