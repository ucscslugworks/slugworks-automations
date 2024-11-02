import json
from getpass import getpass
import time

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

print(r.headers)

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

# print(token)
# print(refreshToken)

headers["Authorization"] = f"Bearer {token}"

decoded_token = jwt.decode(
    token, algorithms=["RS256"], options={"verify_signature": False}
)

expire_time = decoded_token["exp"]
username = decoded_token["username"]

# print(time.time())
# print(expire_time)
# print(username)

r_refresh = requests.post(
    "https://api.bambulab.com/v1/user-service/user/refreshtoken",
    headers=headers,
    json={"refreshToken": f"{refreshToken}"},
)

data = r_refresh.json()
token = data["accessToken"]
refreshToken = data["refreshToken"]
expire_time = int(time.time()) + data["refreshExpiresIn"]

# print(
#     json.dumps(
#         decoded_token,
#         indent=4,
#     )
# )
