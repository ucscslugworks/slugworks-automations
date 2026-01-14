import json
import os
import random
import threading
import time
import traceback

import jwt
import requests

from src import log

# https://github.com/davglass/OpenBambuAPI/blob/main/cloud-http.md

BASE_URL = "https://api.bambulab.com/v1"

LOGIN_URL = f"{BASE_URL}/user-service/user/login"
USER_DATA_URL = f"{BASE_URL}/design-user-service/my/preference"
DEVICES_URL = f"{BASE_URL}/iot-service/api/user/bind"
TASKS_URL = f"{BASE_URL}/user-service/my/tasks"

BAMBU_JSON = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "common",
    "bambu.json",
)

ACCOUNT_OBJECT = None
ACCOUNT_STARTED = False


def get_account():
    global ACCOUNT_OBJECT, ACCOUNT_STARTED

    if not ACCOUNT_STARTED:
        ACCOUNT_STARTED = True
        ACCOUNT_OBJECT = BambuAccount()
        ACCOUNT_OBJECT.logger.info("get_account: Created new BambuAccount object.")
    else:
        while ACCOUNT_OBJECT is None:
            time.sleep(1)

        ACCOUNT_OBJECT.logger.info(
            "get_account: Retrieved existing BambuAccount object."
        )

    return ACCOUNT_OBJECT


class BambuAccount:
    def __init__(self):
        self.logger = log.setup_logs(
            "bambu_account", additional_handlers=[("bambu", log.INFO)]
        )

        self.email = "slugworks@ucsc.edu"

        self.headers = {
            # "User-Agent": random.choice(
            #     json.load(
            #         open(
            #             os.path.join(
            #                 os.path.dirname(os.path.abspath(__file__)),
            #                 "..",
            #                 "..",
            #                 "common",
            #                 "useragents.json",
            #             )
            #         )
            #     )
            # )["ua"]
        }

        self.token = ""
        self.username = ""

        self.latest_task = 0

        self.login()

    @staticmethod
    def _is_jwt(token: str) -> bool:
        # A minimal, safe check: JWTs have 3 segments (2 dots)
        return isinstance(token, str) and token.count(".") == 2

    def login(self):
        try:
            bambu_json = json.load(open(BAMBU_JSON))

            if "token" in bambu_json:
                self.logger.info(
                    "login: Pre-configured token from bambu.json found, will be used"
                )
                self.token = bambu_json["token"]
                self.headers["Authorization"] = f"Bearer {self.token}"

                response = None
                while not response:
                    try:
                        response = requests.get(TASKS_URL, headers=self.headers)
                    except requests.exceptions.ConnectionError:
                        self.logger.error("login: Connection error, retrying...")
                        time.sleep(60)

                self.logger.info(response.status_code)
                if response.status_code != 200:
                    self.logger.info(response.text)
                    self.logger.info(
                        "login: Pre-configured token from bambu.json is invalid, will attempt manual login"
                    )
                    self.token = ""
                else:
                    self.logger.info("login: Logged in using pre-configured token")

            if not self.token:
                self.logger.info(
                    "login: No pre-configured token found or token invalid, attempting manual login"
                )

                if "bambu" not in bambu_json:
                    self.logger.error("login: No password found in bambu.json")
                    exit(1)

                pw = bambu_json["bambu"]

                response = requests.post(
                    LOGIN_URL,
                    json={
                        "account": self.email,
                        "password": pw,
                    },
                    timeout=10,
                )
                response.raise_for_status()

                if response.text and "verifyCode" in response.text:
                    self.logger.info("login: Verification Code requested")
                    if "code" not in bambu_json:
                        self.logger.error("login: No code found in bambu.json")
                        exit(1)

                    code = str(bambu_json["code"])
                    del bambu_json["code"]
                    json.dump(bambu_json, open(BAMBU_JSON, "w"), indent=4)

                    self.logger.info("login: Got code, deleted from bambu.json")

                    response = requests.post(
                        LOGIN_URL,
                        headers=self.headers,
                        json={
                            "account": self.email,
                            "code": code,
                        },
                        timeout=10,
                    )
                    response.raise_for_status()

                resp_json = response.json()
                self.token = resp_json["accessToken"]
                self.expire_time = int(time.time()) + resp_json["expiresIn"]

                self.headers["Authorization"] = f"Bearer {self.token}"

            self.logger.info(f'login: Token: "{self.token}"')

            user_resp = requests.get(USER_DATA_URL, headers=self.headers)
            user_resp.raise_for_status()
            user_json = user_resp.json()
            self.username = f"u_{user_json["uid"]}"

            bambu_json["token"] = self.token
            json.dump(bambu_json, open(BAMBU_JSON, "w"), indent=4)

            self.logger.info("login: Saved token to bambu.json")
        except Exception:
            self.logger.error(f"login: Failed to login: {traceback.format_exc()}")
            exit(1)

    def get_token(self):
        return self.token

    def get_username(self):
        return self.username

    def get_devices(self):
        try:
            response = requests.get(DEVICES_URL, headers=self.headers)
            devices = response.json()["devices"]

            device_data = dict()
            for device in devices:
                device_data[device["name"]] = device["dev_id"]

            self.logger.info(f"get_devices: Got {len(device_data)} devices")

            return device_data
        except Exception:
            self.logger.error(
                f"get_devices: Failed to get devices: {traceback.format_exc()}"
            )
            exit(1)

    def get_tasks(self):
        try:
            response = requests.get(TASKS_URL, headers=self.headers)
            tasks = response.json()["hits"]

            self.logger.info(f"get_tasks: Got {len(tasks)} tasks")

            return tasks
        except Exception:
            self.logger.error(
                f"get_tasks: Failed to get tasks: {traceback.format_exc()}"
            )

    def stop_refresh_thread(self):
        # No background refresh thread currently; provided for compatibility
        try:
            self.logger.info("stop_refresh_thread: No-op (no refresh thread)")
        except Exception:
            pass


if __name__ == "__main__":
    account = get_account()
