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

LOGIN_URL = "https://bambulab.com/api/sign-in/form"
CODE_URL = "https://bambulab.com/api/sign-in/code"
BASE_URL = "https://api.bambulab.com/v1"

REFRESH_TOKEN_URL = f"{BASE_URL}/user-service/user/refreshtoken"
DEVICES_URL = f"{BASE_URL}/iot-service/api/user/bind"
TASKS_URL = f"{BASE_URL}/user-service/my/tasks"

REFRESH_DELAY = 30  # seconds

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
            "User-Agent": random.choice(
                json.load(
                    open(
                        os.path.join(
                            os.path.dirname(os.path.abspath(__file__)),
                            "..",
                            "..",
                            "common",
                            "useragents.json",
                        )
                    )
                )
            )["ua"]
        }

        self.token = ""
        self.refresh_token = ""
        self.username = ""
        self.expire_time = -1

        self.refresh_thread = None
        self.stop_refresh_loop = False
        self.latest_task = 0

        self.login()

    def login(self):
        try:
            bambu_json = json.load(
                open(
                    BAMBU_JSON,
                )
            )

            if "token" in bambu_json and "refreshToken" in bambu_json:
                self.logger.info(
                    "login: Pre-configured token from bambu.json found, will be used"
                )
                self.token = bambu_json["token"]
                self.refresh_token = bambu_json["refreshToken"]
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
                    self.refresh_token = ""
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
                    headers=self.headers,
                    data={
                        "account": self.email,
                        "password": pw,
                        "apiError": "",
                    },
                )

                if response.text and "verifyCode" in response.text:
                    self.logger.info("login: Verification Code requested")
                    if "code" not in bambu_json:
                        self.logger.error("login: No code found in bambu.json")
                        exit(1)

                    code = bambu_json["code"]
                    del bambu_json["code"]
                    json.dump(
                        bambu_json,
                        open(
                            BAMBU_JSON,
                            "w",
                        ),
                    )

                    self.logger.info("login: Got code, deleted from bambu.json")

                    response = requests.post(
                        CODE_URL,
                        headers=self.headers,
                        data={
                            "account": self.email,
                            "password": pw,
                            "code": code,
                            "apiError": "",
                        },
                    )

                if response.text and (
                    "cloudflare" in response.text or "challenge" in response.text
                ):
                    self.logger.error(
                        "login: Cloudflare blocking may have occurred. Please generate the token manually and save it in bambu.json"
                    )
                    exit(1)
                else:
                    self.logger.info(
                        "login: Login may have been successful, attempting to parse headers"
                    )

                if "token" not in response.headers["Set-Cookie"]:
                    self.logger.error("login: Failed to login - no token received")
                    exit(1)

                for h in response.headers["Set-Cookie"].split("; "):
                    if h.startswith("refreshToken="):
                        self.refresh_token = h[len("refreshToken=") :]
                    elif h.startswith("Secure, token="):
                        self.token = h[len("Secure, token=") :]

                self.headers["Authorization"] = f"Bearer {self.token}"

            self.logger.info(f'login: Token: "{self.token}"')
            self.logger.info(f'login: Refresh Token: "{self.refresh_token}"')

            decoded_token = jwt.decode(
                self.token, algorithms=["RS256"], options={"verify_signature": False}
            )

            self.logger.info("login: Headers and token successfully parsed")

            self.expire_time = decoded_token["exp"]
            self.username = decoded_token["username"]

            self.logger.info(
                f"login: Token expires at {time.strftime("%Y-%m-%d %H:%M:%S %z", time.gmtime(self.expire_time))}"
            )
            self.logger.info(f"login: Logged in as {self.username}")

            bambu_json["token"] = self.token
            bambu_json["refreshToken"] = self.refresh_token
            json.dump(
                bambu_json,
                open(
                    BAMBU_JSON,
                    "w",
                ),
            )

            self.logger.info("login: Saved token to bambu.json")

            self.refresh_thread = threading.Thread(target=self.refresh_loop)
            self.refresh_thread.start()

            self.logger.info("login: Started refresh thread")
        except Exception:
            self.logger.error(f"login: Failed to login: {traceback.format_exc()}")
            exit(1)

    def refresh(self):
        try:
            response = requests.post(
                REFRESH_TOKEN_URL,
                headers=self.headers,
                json={"refreshToken": f"{self.refresh_token}"},
            )

            data = response.json()

            self.token = data["accessToken"]
            self.refresh_token = data["refreshToken"]
            self.expire_time = int(time.time()) + data["refreshExpiresIn"]

            self.logger.info(f'login: Token: "{self.token}"')
            self.logger.info(f'login: Refresh Token: "{self.refresh_token}"')
            self.logger.info(
                f"login: Token expires at {time.strftime("%Y-%m-%d %H:%M:%S %z", time.gmtime(self.expire_time))}"
            )

            self.headers["Authorization"] = f"Bearer {self.token}"

            bambu_json = json.load(
                open(
                    BAMBU_JSON,
                    "r",
                ),
            )
            bambu_json["token"] = self.token
            bambu_json["refreshToken"] = self.refresh_token
            json.dump(
                bambu_json,
                open(
                    BAMBU_JSON,
                    "w",
                ),
            )

            self.logger.info("refresh: Refreshed token and saved to bambu.json")
        except Exception:
            self.logger.error(
                f"refresh: Failed to refresh token: {traceback.format_exc()}"
            )
            exit(1)

    def refresh_loop(self):
        while not self.stop_refresh_loop:
            try:
                if self.expire_time - int(time.time()) < REFRESH_DELAY * 2:
                    self.refresh()

                time.sleep(REFRESH_DELAY)
            except Exception:
                self.logger.error(
                    f"refresh_loop: Refresh loop error: {traceback.format_exc()}"
                )
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
        try:
            if self.refresh_thread:
                self.stop_refresh_loop = True
                self.refresh_thread.join()
                self.logger.info("stop_refresh_thread: Stopped refresh thread")
            else:
                self.logger.error("stop_refresh_thread: No refresh thread to stop")
        except Exception:
            self.logger.error(
                f"stop_refresh_thread: Failed to stop refresh thread: {traceback.format_exc()}"
            )
            exit(1)


if __name__ == "__main__":
    account = get_account()
