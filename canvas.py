import json
from datetime import datetime, timedelta

import requests

import sheet


def update():
    sheet.get_sheet_data(limited=False)
    print("Successfully retrieved sheet data")

    keys = json.load(open("canvas.json"))

    token = keys["canvas_auth_token"]
    course_id = keys["canvas_course_id"]

    url = f"https://canvas.ucsc.edu/api/v1/courses/{course_id}/"
    endpoint = "students" # TODO: replace with https://canvas.instructure.com/doc/api/all_resources.html#method.courses.users this endpoint, and get both students and staff to populate both sheets & check for duplicates
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.request("GET", url + endpoint, headers=headers)

    students_json = json.loads(response.text)
    students = {}
    for s in students_json:
        # TODO: check if student is a staff member, and if so, skip them
        
        if (
            "login_id" not in s
            or "ucsc.edu" not in s["login_id"]
            or s["login_id"] in students
        ):
            continue

        cruzid = s["login_id"].split("@ucsc.edu")[0]

        if sheet.is_staff(cruzid):
            continue

        if not sheet.student_exists(cruzid):
            sn = s["sortable_name"].split(", ")
            students[cruzid] = s["id"]
            sheet.new_student(sn[1], sn[0], cruzid, s["id"])

        students[cruzid] = s["id"]

    print("Successfully retrieved student data from Canvas")

    endpoint = "modules"

    for cruzid in students:
        data = {"student_id": students[cruzid]}
        response = requests.request("GET", url + endpoint, headers=headers, data=data)
        modules_json = json.loads(response.text)
        completed_modules = []
        for m in modules_json:
            if m["state"] == "completed":
                completed_modules.append(int(m["position"]))

        sheet.evaluate_modules(completed_modules, cruzid)
        print(f"Successfully evaluated modules for {cruzid}")

    print("\nSuccessfully evaluated modules for all students")

    if sheet.write_student_sheet():
        print("Successfully wrote student sheet")
    else:
        print("Failed to write student sheet")
        return False

    if sheet.log("Canvas Update", "", False, 0):
        print("Successfully logged canvas update")
    else:
        print("Failed to log canvas update")
        return False

    return True


CANVAS_UPDATE_HOUR = 0  # 12am
CHECKIN_TIMEOUT = 5  # 5 minutes

if __name__ == "__main__":
    # update()
    while True:
        if (
            not sheet.last_update_date or datetime.now().date() > sheet.last_update_date
        ) and datetime.now().hour >= CANVAS_UPDATE_HOUR:
            print("Canvas update...")
            # update()
            sheet.get_sheet_data()
            sheet.check_in()
        elif (
            not sheet.last_checkin_time
            or datetime.now() - sheet.last_checkin_time
            > timedelta(0, 0, 0, 0, CHECKIN_TIMEOUT, 0, 0)
        ):
            print("Checking in...")
            sheet.check_in()
