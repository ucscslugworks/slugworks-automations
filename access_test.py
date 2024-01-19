import json

import requests

# out_file = open("out.json", "w")

keys = json.load(open("keys.json"))

token = keys["canvas_auth_token"]
course_id = "67429"

url = f"https://canvas.ucsc.edu/api/v1/courses/{course_id}/"
# endpoint = "students"
# endpoint = "bulk_user_progress"
endpoint = "modules/158619"

headers = {"Authorization": f"Bearer {token}"}
data = {"student_id": "57198"}

response = requests.request("GET", url + endpoint, headers=headers, data=data)
print(json.dumps(json.loads(response.text), indent=4, sort_keys=True))

# out_file.write(json.dumps(json.loads(response.text), indent=4, sort_keys=True))
# print("students")
# students_json = json.loads(response.text)
# students = []
# for s in students_json:
#     sn = s["sortable_name"].split(", ")
#     students.append((sn[1], sn[0], s["login_id"].split("@ucsc.edu")[0], s["id"]))

# endpoint = "modules"

# for s in students:
#     print(s)
#     first = s[0]
#     last = s[1]
#     cruzid = s[2]
#     student_id = s[3]
#     data = {"student_id": student_id}
#     response = requests.request("GET", url + endpoint, headers=headers, data=data)
#     out_file.write(json.dumps(json.loads(response.text), indent=4, sort_keys=True))

# out_file.close()

key = "AIzaSyDFOTpZuNpjBcTE2OLd5b4zop4kzvh1JwQ"