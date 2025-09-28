import json
import os
import random
import threading
import time
import traceback
from http.cookies import SimpleCookie

import jwt
import requests

from src import log
# import paho.mqtt.client as mqtt
# mqtt.Client.enable_logger()

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

        # Load bambu.json early (for CF cookies, saved usernames, etc.)
        bambu_json = self._load_bambu_json()

        # Pick a browsery UA from your useragents.json
        try:
            uas = json.load(
                open(
                    os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        "..",
                        "..",
                        "common",
                        "useragents.json",
                    ),
                    "r",
                )
            )
            ua = random.choice(uas)["ua"]
        except Exception:
            ua = "Mozilla/5.0"

        # Base headers we’ll merge per request (no Authorization here)
        self.headers = {
            "User-Agent": ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://bambulab.com",
            "Referer": "https://bambulab.com/",
        }

        # One session for all requests so cookies/CF handshake stick
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # Carry CF cookies if provided
        cf_clearance = bambu_json.get("cf_clearance")
        cf_bm = bambu_json.get("__cf_bm") or bambu_json.get("cf_bm")
        if cf_clearance:
            self.session.cookies.set(
                "cf_clearance", cf_clearance, domain=".bambulab.com", path="/", secure=True
            )
        if cf_bm:
            self.session.cookies.set(
                "__cf_bm", cf_bm, domain=".bambulab.com", path="/", secure=True
            )

        self.token = bambu_json.get("token", "")
        # after determining self.token
        self.headers["Authorization"] = f"Bearer {self.token}"
        self.session.headers["Authorization"] = f"Bearer {self.token}"

        self.refresh_token = bambu_json.get("refreshToken", "")
        # Prefer a previously saved mqtt_username; otherwise we'll decide later
        self.username = (bambu_json.get("mqtt_username") or "").strip()
        # -1 means "unknown" (e.g. opaque token)
        self.expire_time = -1

        self.refresh_thread = None
        self.stop_refresh_loop = False
        self.latest_task = 0

        self.login()

    # ---------- helpers ----------

    @staticmethod
    def _load_bambu_json() -> dict:
        try:
            with open(BAMBU_JSON, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def _save_bambu_json(data: dict):
        try:
            with open(BAMBU_JSON, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    @staticmethod
    def _is_jwt(token: str) -> bool:
        # Minimal, safe check: JWTs have exactly 3 segments (2 dots)
        return isinstance(token, str) and token.count(".") == 2

    def _warm_up_cloudflare(self):
        # Touch root domain to get CF to set any additional cookies
        try:
            self.session.get("https://bambulab.com/", timeout=10)
        except Exception as e:
            self.logger.debug(f"warm_up_cloudflare: root warmup failed: {e}")

        # Persist any new CF cookies back to bambu.json
        try:
            bj = self._load_bambu_json()
            cj = self.session.cookies
            new_cf = cj.get("cf_clearance", domain=".bambulab.com", path="/")
            new_bm = cj.get("__cf_bm", domain=".bambulab.com", path="/")
            changed = False
            if new_cf and bj.get("cf_clearance") != new_cf:
                bj["cf_clearance"] = new_cf
                changed = True
            if new_bm and bj.get("__cf_bm") != new_bm:
                bj["__cf_bm"] = new_bm
                changed = True
            if changed:
                self._save_bambu_json(bj)
                self.logger.info("warm_up_cloudflare: updated CF cookies in bambu.json")
        except Exception as e:
            self.logger.debug(f"warm_up_cloudflare: cookie persist skipped: {e}")

    @staticmethod
    def _mask(tok: str, show_start=6, show_end=4) -> str:
        if not tok:
            return "<empty>"
        if len(tok) <= show_start + show_end:
            return tok
        return f"{tok[:show_start]}...{tok[-show_end:]}"

    # ---------- main flow ----------

    def login(self):
        try:
            bj = self._load_bambu_json()

            # Cloudflare warm-up first
            self._warm_up_cloudflare()

            # If preconfigured token present, try it
            if self.token and self.refresh_token:
                self.logger.info("login: Using pre-configured token from bambu.json")
                probe_headers = {**self.headers, "Authorization": f"Bearer {self.token}"}
                response = None
                while response is None:
                    try:
                        response = self.session.get(TASKS_URL, headers=probe_headers, timeout=15)
                    except requests.exceptions.ConnectionError:
                        self.logger.error("login: Connection error, retrying in 60s...")
                        time.sleep(60)

                if response.status_code != 200:
                    self.logger.info(f"login: token probe failed: {response.status_code}")
                    try:
                        self.logger.debug(f"login: body: {response.text[:500]}")
                    except Exception:
                        pass
                    self.logger.info("login: Will attempt manual login.")
                    self.token = ""
                    self.refresh_token = ""
                else:
                    self.logger.info("login: Logged in using pre-configured token")

            # Manual login if needed
            if not self.token:
                self.logger.info("login: Attempting manual login")

                if "bambu" not in bj:
                    self.logger.error("login: No password found in bambu.json")
                    raise SystemExit(1)

                pw = bj["bambu"]

                resp = self.session.post(
                    LOGIN_URL,
                    data={
                        "account": self.email,
                        "password": pw,
                        "apiError": "",
                    },
                    timeout=20,
                )

                # 2FA code flow
                if resp.text and "verifyCode" in resp.text:
                    self.logger.info("login: Verification Code requested")
                    if "code" not in bj:
                        self.logger.error("login: No code found in bambu.json")
                        raise SystemExit(1)

                    code = bj["code"]
                    # Remove code once used
                    del bj["code"]
                    self._save_bambu_json(bj)
                    self.logger.info("login: Got code, deleted from bambu.json")

                    resp = self.session.post(
                        CODE_URL,
                        data={
                            "account": self.email,
                            "password": pw,
                            "code": code,
                            "apiError": "",
                        },
                        timeout=20,
                    )

                # Basic CF detection
                if resp.text and ("cloudflare" in resp.text.lower() or "challenge" in resp.text.lower()):
                    self.logger.error(
                        "login: Cloudflare challenge detected. Generate token manually and save to bambu.json"
                    )
                    raise SystemExit(1)

                # Parse cookies robustly
                token_cookie = resp.cookies.get("token")
                refresh_cookie = resp.cookies.get("refreshToken")

                # Fallback: try raw headers if needed
                if (not token_cookie or not refresh_cookie) and "Set-Cookie" in resp.headers:
                    sc = resp.headers.get("Set-Cookie", "")
                    cookie = SimpleCookie()
                    cookie.load(sc)
                    if not token_cookie and "token" in cookie:
                        token_cookie = cookie["token"].value
                    if not refresh_cookie and "refreshToken" in cookie:
                        refresh_cookie = cookie["refreshToken"].value

                if not token_cookie or not refresh_cookie:
                    self.logger.error("login: Failed to login - no token received")
                    raise SystemExit(1)

                self.token = token_cookie
                self.refresh_token = refresh_cookie

            # === JWT SAFEGUARD ===
            if self._is_jwt(self.token):
                try:
                    decoded = jwt.decode(
                        self.token, algorithms=["RS256"], options={"verify_signature": False}
                    )
                    self.expire_time = decoded.get("exp", -1)
                    # Prefer explicit JWT username if present
                    jwt_username = decoded.get("username") or decoded.get("email") or decoded.get("sub")
                    if not self.username:
                        self.username = (jwt_username or self.email) or ""
                    self.logger.info(
                        f"login: JWT token parsed; exp={self.expire_time if self.expire_time != -1 else 'unknown'}; user={self.username or '<unset>'}"
                    )
                except Exception as e:
                    self.logger.info(f"login: JWT present but could not decode safely: {e}")
                    self.expire_time = -1
                    if not self.username:
                        self.username = self.email
            else:
                # Opaque token: cannot decode, so skip JWT fields gracefully.
                self.logger.info("login: Opaque token detected — skipping jwt.decode.")
                self.expire_time = -1
                if not self.username:
                    self.username = self.email

            # Persist tokens + chosen MQTT username
            bj["token"] = self.token
            bj["refreshToken"] = self.refresh_token
            bj["mqtt_username"] = self.username
            self._save_bambu_json(bj)

            self.logger.info(f'login: Token set ({self._mask(self.token)})')
            self.logger.info(f'login: Refresh Token set ({self._mask(self.refresh_token)})')
            self.logger.info(f'login: MQTT username = "{self.username}"')

            # Start refresh thread
            self.refresh_thread = threading.Thread(target=self.refresh_loop, daemon=True)
            self.refresh_thread.start()
            self.logger.info("login: Started refresh thread")

        except SystemExit:
            raise
        except Exception:
            self.logger.error(f"login: Failed to login: {traceback.format_exc()}")
            raise SystemExit(1)

    def refresh(self):
        try:
            # IMPORTANT: Do NOT send Authorization header for refresh
            resp = self.session.post(
                REFRESH_TOKEN_URL,
                json={"refreshToken": f"{self.refresh_token}"},
                timeout=15,
            )

            if resp.status_code != 200:
                self.logger.error(f"refresh: HTTP {resp.status_code}")
                try:
                    self.logger.debug(f"refresh: body: {resp.text[:500]}")
                except Exception:
                    pass
                raise SystemExit(1)

            data = resp.json()

            self.token = data["accessToken"]
            self.refresh_token = data["refreshToken"]

            # If the response contains absolute expiries, prefer them. Otherwise fall back.
            now = int(time.time())
            self.expire_time = now + int(data.get("refreshExpiresIn", 0) or 0)

            self.logger.info(f'refresh: New token ({self._mask(self.token)})')
            self.logger.info(f'refresh: New refreshToken ({self._mask(self.refresh_token)})')
            self.logger.info(
                f"refresh: Token expires at {time.strftime('%Y-%m-%d %H:%M:%S %z', time.gmtime(self.expire_time))}"
            )

            # Choose/keep MQTT username: prefer persisted or prior, else email
            bj = self._load_bambu_json()
            cfg_username = (bj.get("mqtt_username") or "").strip()
            if cfg_username:
                self.username = cfg_username
            elif not self.username:
                self.username = self.email

            # Persist updates
            bj["token"] = self.token
            bj["refreshToken"] = self.refresh_token
            bj["mqtt_username"] = self.username
            self._save_bambu_json(bj)

            self.logger.info(f'refresh: MQTT username = "{self.username}" (persisted)')

        except SystemExit:
            raise
        except Exception:
            self.logger.error(
                f"refresh: Failed to refresh token: {traceback.format_exc()}"
            )
            raise SystemExit(1)

    def refresh_loop(self):
        while not self.stop_refresh_loop:
            try:
                # Only attempt time-based refresh if we actually know an expiry.
                if self.expire_time >= 0 and (self.expire_time - int(time.time()) < REFRESH_DELAY * 2):
                    self.refresh()

                time.sleep(REFRESH_DELAY)
            except SystemExit:
                raise
            except Exception:
                self.logger.error(
                    f"refresh_loop: Refresh loop error: {traceback.format_exc()}"
                )
                raise SystemExit(1)

    # ---------- public API used elsewhere ----------

    def get_token(self):
        return self.token

    def get_username(self):
        return self.username

    def get_devices(self):
        try:
            headers = {**self.headers, "Authorization": f"Bearer {self.token}"}
            response = self.session.get(DEVICES_URL, headers=headers, timeout=15)
            response.raise_for_status()
            devices = response.json().get("devices", [])

            device_data = dict()
            for device in devices:
                device_data[device.get("name")] = device.get("dev_id")

            self.logger.info(f"get_devices: Got {len(device_data)} devices")
            return device_data
        except Exception:
            self.logger.error(
                f"get_devices: Failed to get devices: {traceback.format_exc()}"
            )
            raise SystemExit(1)
    def get_device_access_code(self, dev_id: str):
        try:
            # session first (carries CF cookies + bearer), then fallback
            resp = self.session.get(DEVICES_URL, timeout=15)
            if resp.status_code == 401:
                resp = requests.get(DEVICES_URL, headers=self.headers, timeout=15)
            resp.raise_for_status()
            for d in resp.json().get("devices", []):
                if d.get("dev_id") == dev_id:
                    ac = d.get("dev_access_code")
                    return ac.strip() if isinstance(ac, str) else None
        except Exception:
            self.logger.error(f"get_device_access_code: Failed: {traceback.format_exc()}")
        return None



    def get_tasks(self):
        try:
            headers = {**self.headers, "Authorization": f"Bearer {self.token}"}
            response = self.session.get(TASKS_URL, headers=headers, timeout=15)
            response.raise_for_status()
            tasks = response.json().get("hits", [])
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
                self.refresh_thread.join(timeout=3)
                self.logger.info("stop_refresh_thread: Stopped refresh thread")
            else:
                self.logger.error("stop_refresh_thread: No refresh thread to stop")
        except Exception:
            self.logger.error(
                f"stop_refresh_thread: Failed to stop refresh thread: {traceback.format_exc()}"
            )
            raise SystemExit(1)


if __name__ == "__main__":
    account = get_account()
