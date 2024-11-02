import json
import time
from getpass import getpass

import jwt
import requests

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

r = requests.post(
    "https://bambulab.com/api/sign-in/form",
    headers=headers,
    data={
        "account": "email",
        "password": getpass(),
    },
)

# print(r.headers)

if "token" not in r.headers["Set-Cookie"]:
    print("Failed to login")
    exit(1)

refreshToken = ""
token = ""
for h in r.headers["Set-Cookie"].split("; "):
    if h.startswith("refreshToken="):
        refreshToken = h[len("refreshToken=") :]
    elif h.startswith("Secure, token="):
        token = h[len("Secure, token=") :]

headers["Authorization"] = f"Bearer {token}"

decoded_token = jwt.decode(
    token, algorithms=["RS256"], options={"verify_signature": False}
)

expire_time = decoded_token["exp"]
username = decoded_token["username"]

r_refresh = requests.post(
    "https://api.bambulab.com/v1/user-service/user/refreshtoken",
    headers=headers,
    json={"refreshToken": f"{refreshToken}"},
)

data = r_refresh.json()

token = data["accessToken"]
refreshToken = data["refreshToken"]
expire_time = int(time.time()) + data["refreshExpiresIn"]

headers["Authorization"] = f"Bearer {token}"

r_tasks = requests.get(
    "https://api.bambulab.com/v1/user-service/my/tasks", headers=headers
)

cover_url = r_tasks.json()["hits"][-1]["cover"]

headers.pop("Authorization")
r_cover = requests.get(cover_url, headers=headers, stream=True)
if r_cover.status_code == 200:
    with open("cover.png", "wb") as f:
        for chunk in r_cover:
            f.write(chunk)
else:
    print("Failed to download cover")
    print(r_cover.status_code)
    print(r_cover.text)
    exit(1)