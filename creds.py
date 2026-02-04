import json
import os
import random

import requests

# LOGIN_URL = "https://api.bambulab.com/v1/user-service/user/login"
token = "AAAcxkb5YKR6hNPW_YQP1Pdklfu-rt7GZxu5oA6wdPPlX-aFjWm-401ChCvsHn8m3FRdg4txLXz9cBT7pct0IVhbdsCP4daR5PfTz-aW622M3ZShuO_cu5YwDCaDdvSf9KzLZosSWDjKzcl7"

headers = {
    "User-Agent": random.choice(
        json.load(
            open(
                os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "common",
                    "useragents.json",
                )
            )
        )
    )["ua"],
    "Authorization": "Bearer " + token,
}

# response = requests.post(
#     LOGIN_URL,
#     # headers=headers,
#     json={
#         "account": "slugworks@ucsc.edu",
#         # "password": "WorkingNine2Five!",
#         "code": "110573"
#     },
# )

# print(response.text)

# response = requests.get(
#     "https://api.bambulab.com/v1/user-service/my/tasks", headers=headers
# )
# print(response.text)


response = requests.post(
    "https://api.bambulab.com/v1/user-service/user/refreshtoken",
    headers=headers,
    json={"refreshToken": token},
)

print(response.text)
