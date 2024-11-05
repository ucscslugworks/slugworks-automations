import json
import time
from getpass import getpass

import jwt
import requests

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# r = requests.post(
#     "https://bambulab.com/api/sign-in/code",
#     headers=headers,
#     data={
#         "account": "slugworks@ucsc.edu",
#         "password": getpass(),
#         "code": "858730"
#     },
# )

# # print(r.headers)

# if "token" not in r.headers["Set-Cookie"]:
#     print("Failed to login")
#     exit(1)

# refreshToken = ""
# token = ""
# for h in r.headers["Set-Cookie"].split("; "):
#     if h.startswith("refreshToken="):
#         refreshToken = h[len("refreshToken=") :]
#     elif h.startswith("Secure, token="):
#         token = h[len("Secure, token=") :]

token = "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICI4OV8zYTZqeWl4LWFKa2I0V1prVmNqM0ZGR1dMRU5DWUpjT2hkMWYzVl8wIn0.eyJleHAiOjE3NjE4OTcyOTYsImlhdCI6MTczMDc5MzI5NiwianRpIjoiNTMzNGI0OTgtYWI5Yy00MWI4LWIzMzktZjQ5MDQ1MTkwNjI2IiwiaXNzIjoiaHR0cDovL2tleWNsb2FrLWh0dHAua2V5Y2xvYWstcHJvZC11cy9hdXRoL3JlYWxtcy9iYmwiLCJhdWQiOiJhY2NvdW50Iiwic3ViIjoiYTAxMGMxMjgtMWE2OC00NDIwLThmZDAtZTk2NGMwMDcxY2JlIiwidHlwIjoiQmVhcmVyIiwiYXpwIjoidXNlci1zZXJ2aWNlIiwic2Vzc2lvbl9zdGF0ZSI6IjAxYWYzMzhmLTdmMWUtNDRkMC05ZWI2LTlhMTgxZDZiM2FiNyIsInJlYWxtX2FjY2VzcyI6eyJyb2xlcyI6WyJvZmZsaW5lX2FjY2VzcyIsInVtYV9hdXRob3JpemF0aW9uIiwiZGVmYXVsdC1yb2xlcy1iYmwiXX0sInJlc291cmNlX2FjY2VzcyI6eyJhY2NvdW50Ijp7InJvbGVzIjpbIm1hbmFnZS1hY2NvdW50IiwibWFuYWdlLWFjY291bnQtbGlua3MiLCJ2aWV3LXByb2ZpbGUiXX19LCJzY29wZSI6ImVtYWlsIHByb2ZpbGUiLCJzaWQiOiIwMWFmMzM4Zi03ZjFlLTQ0ZDAtOWViNi05YTE4MWQ2YjNhYjciLCJlbWFpbF92ZXJpZmllZCI6ZmFsc2UsInByZWZlcnJlZF91c2VybmFtZSI6Il8yOTYxMjQyNzY0IiwidXNlcm5hbWUiOiJ1XzI5NjEyNDI3NjQifQ.IH6XGmTbKwjLuExE74Jg-ptTzyqTt0x_Qlc56KBYMd9afrCvoXOW9p24gfE0oigpU4pU6EhHoxAFvz2_fwfKS5ALDExZ6qd4ahzTqJRgkr1z5sqJL0SKvR821m-GUd2kPLsw0SzmAxJokldEihdmgwjzcw9Uc_b4gi4rLFoyMhr1H11BiKv44eF_7KNz1aoMOFjoIuAdA8jsNnG8_0eP1Ro70skLoCWQj-iyuB9KUC7GRCd5BwJTWIIWnWiHvLRe5ZUQ01ET-R8Df4IhYV-s9seo2lY3JgCafjG5izn_GTHOxFdFf09Eb-FpY5trS5JCNecv4pnkmyHXCUHHaMchow"

headers["Authorization"] = f"Bearer {token}"

decoded_token = jwt.decode(
    token, algorithms=["RS256"], options={"verify_signature": False}
)

expire_time = decoded_token["exp"]
username = decoded_token["username"]

# r_refresh = requests.post(
#     "https://api.bambulab.com/v1/user-service/user/refreshtoken",
#     headers=headers,
#     json={"refreshToken": f"{refreshToken}"},
# )

# data = r_refresh.json()

# token = data["accessToken"]
# refreshToken = data["refreshToken"]
# expire_time = int(time.time()) + data["refreshExpiresIn"]

# headers["Authorization"] = f"Bearer {token}"

r_tasks = requests.get(
    "https://api.bambulab.com/v1/user-service/my/tasks", headers=headers
)

print(json.dumps(r_tasks.json(), indent=4))
print(r_tasks.status_code)

# cover_url = r_tasks.json()["hits"][-1]["cover"]

# headers.pop("Authorization")
# r_cover = requests.get(cover_url, headers=headers, stream=True)
# if r_cover.status_code == 200:
#     with open("cover.png", "wb") as f:
#         for chunk in r_cover:
#             f.write(chunk)
# else:
#     print("Failed to download cover")
#     print(r_cover.status_code)
#     print(r_cover.text)
#     exit(1)
