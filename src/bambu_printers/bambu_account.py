import json
import os
import threading
import time
from getpass import getpass

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


class BambuAccount:
    def __init__(self, email: str):
        self.logger = log.setup_logs("bambu_account")

        self.email = email

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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
            pw = json.load(
                open(
                    os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        "..",
                        "..",
                        "common",
                        "bambu.json",
                    )
                )
            )["bambu"]

            code = json.load(
                open(
                    os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        "..",
                        "..",
                        "common",
                        "bambu.json",
                    )
                )
            )["code"]

            response = requests.post(
                LOGIN_URL,
                headers=self.headers,
                data={
                    "account": self.email,
                    "password": pw,
                    "apiError": "",
                },
            )

            if response.json() and response.json()["loginType"] == "verifyCode":
                response = requests.post(
                    CODE_URL,
                    headers=self.headers,
                    data={
                        "account": self.email,
                        "password": pw,
                        "apiError": "",
                        "code": code,
                    },
                )

            if "token" not in response.headers["Set-Cookie"]:
                self.logger.error("login: Failed to login")
                exit(1)

            for h in response.headers["Set-Cookie"].split("; "):
                if h.startswith("refreshToken="):
                    self.refresh_token = h[len("refreshToken=") :]
                elif h.startswith("Secure, token="):
                    self.token = h[len("Secure, token=") :]

            self.headers["Authorization"] = f"Bearer {self.token}"

            decoded_token = jwt.decode(
                self.token, algorithms=["RS256"], options={"verify_signature": False}
            )

            self.expire_time = decoded_token["exp"]
            self.username = decoded_token["username"]

            self.logger.info(f"login: Logged in as {self.username}")

            self.refresh_thread = threading.Thread(target=self.refresh_loop)
            self.refresh_thread.start()

            self.logger.info("login: Started refresh thread")
        except Exception as e:
            self.logger.error(f"login: Failed to login: {type(e)} {e}")
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

            self.headers["Authorization"] = f"Bearer {self.token}"

            self.logger.info("refresh: Refreshed token")
        except Exception as e:
            self.logger.error(f"refresh: Failed to refresh token: {type(e)} {e}")
            exit(1)

    def refresh_loop(self):
        while not self.stop_refresh_loop:
            try:
                if self.expire_time - int(time.time()) < REFRESH_DELAY * 2:
                    self.refresh()

                time.sleep(REFRESH_DELAY)
            except Exception as e:
                self.logger.error(f"refresh_loop: Refresh loop error: {type(e)} {e}")
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
        except Exception as e:
            self.logger.error(f"get_devices: Failed to get devices: {type(e)} {e}")
            exit(1)

    def get_tasks(self):
        try:
            response = requests.get(TASKS_URL, headers=self.headers)
            tasks = response.json()["hits"]

            tasks = [t for t in tasks if t["id"] > self.latest_task]
            if tasks:
                self.latest_task = tasks[0]["id"]

            self.logger.info(f"get_tasks: Got {len(tasks)} tasks")

            return tasks
        except Exception as e:
            self.logger.error(f"get_tasks: Failed to get tasks: {type(e)} {e}")

    def stop_refresh_thread(self):
        if self.refresh_thread:
            self.stop_refresh_loop = True
            self.refresh_thread.join()
            self.logger.info("stop_refresh_thread: Stopped refresh thread")
        else:
            self.logger.error("stop_refresh_thread: No refresh thread to stop")
