import json

import requests

keys = json.load(open("keys.json"))

token = keys["canvas_auth_token"]
course_id = "70916"

# url = "https://canvas.ucsc.edu/api/v1/courses"
# url = f"https://canvas.ucsc.edu/api/v1/courses/{course_id}/assignments"
url = f"https://canvas.ucsc.edu/api/v1/courses/{course_id}/students"

headers = {"Authorization": f"Bearer {token}"}

response = requests.request("GET", url, headers=headers)

# data = {"access_token": token}
# response = requests.request("GET", url, data=data)

students_json = json.loads(response.text)
students = []
for s in students_json:
    sn = s["sortable_name"].split(", ")
    students.append((sn[1], sn[0], s["login_id"].split("@ucsc.edu")[0], s["id"]))


url = "https://canvas.ucsc.edu/api/v1/courses/70916/modules"
for s in students:
    first = s[0]
    last = s[1]
    cruzid = s[2]
    student_id = s[3]
    data = {"student_id": student_id}
    response = requests.request("GET", url, headers=headers, data=data)
    print(json.dumps(json.loads(response.text), indent=4, sort_keys=True))

# print(students)
