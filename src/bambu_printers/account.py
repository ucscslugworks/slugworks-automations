import logging
import threading
import time
from getpass import getpass

import jwt
import requests

# https://github.com/davglass/OpenBambuAPI/blob/main/cloud-http.md

LOGIN_URL = "https://bambulab.com/api/sign-in/form"
BASE_URL = "https://api.bambulab.com/v1"

REFRESH_TOKEN_URL = f"{BASE_URL}/user-service/user/refreshtoken"
DEVICES_URL = f"{BASE_URL}/iot-service/api/user/bind"
TASKS_URL = f"{BASE_URL}/user-service/my/tasks"

REFRESH_DELAY = 30  # seconds


class BambuAccount:
    def __init__(self, email: str, logger: logging.Logger):
        self.email = email
        self.password = getpass()

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        self.token = ""
        self.refresh_token = ""
        self.username = ""
        self.expire_time = -1

        self.logger = logger

        self.refresh_thread = None

        self.login()

    def login(self):
        try:
            response = requests.post(
                LOGIN_URL,
                headers=self.headers,
                data={"account": self.email, "password": self.password},
            )

            if "token" not in response.headers["Set-Cookie"]:
                self.logger.error("Failed to login")
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

            self.logger.info(f"Logged in as {self.username}")

            self.refresh_thread = threading.Thread(target=self.refresh_loop)
            self.refresh_thread.start()
        except Exception as e:
            self.logger.error(f"BambuAccount: Failed to login: {e}")
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

            self.logger.info("BambuAccount: Refreshed token")
        except Exception as e:
            self.logger.error(f"BambuAccount: Failed to refresh token: {e}")
            exit(1)

    def refresh_loop(self):
        while True:
            try:
                if self.expire_time - int(time.time()) < REFRESH_DELAY * 2:
                    self.refresh()

                time.sleep(REFRESH_DELAY)
            except Exception as e:
                self.logger.error(f"BambuAccount: Refresh loop error: {e}")
                exit(1)

    def get_devices(self):
        try:
            response = requests.get(DEVICES_URL, headers=self.headers)
            devices = response.json()["devices"]

            self.logger.info(f"BambuAccount: Got {len(devices)} devices")

            device_data = dict()
            for device in devices:
                device_data[device["name"]] = device["dev_id"]

            return device_data
        except Exception as e:
            self.logger.error(f"BambuAccount: Failed to get devices: {e}")
            exit(1)

    def get_tasks(self, limit: int | None = None):
        try:
            if limit is None:
                response = requests.get(TASKS_URL, headers=self.headers)
            else:
                response = requests.get(
                    TASKS_URL, headers=self.headers, params={"limit": limit}
                )

            self.logger.info(f"BambuAccount: Got {response.json()['total']} tasks")

            return response.json()["total"], response.json()["hits"]
        except Exception as e:
            self.logger.error(f"BambuAccount: Failed to get tasks: {e}")
