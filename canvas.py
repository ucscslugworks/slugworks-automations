import json
import time
from datetime import datetime, timedelta

import requests

import sheet


def list_modules():
    keys = json.load(open("canvas.json"))

    token = keys["auth_token"]
    course_id = keys["course_id"]

    url = f"https://canvas.ucsc.edu/api/v1/courses/{course_id}/"
    headers = {"Authorization": f"Bearer {token}"}

    endpoint = "modules"

    params = {
        "per_page": 1000,
    }

    response = requests.request("GET", url + endpoint, headers=headers, params=params)

    print(json.dumps(response.json(), indent=4))


def update():
    try:
        sheet.get_sheet_data(limited=False)
        print("Successfully retrieved sheet data")

        keys = json.load(open("canvas.json"))

        token = keys["auth_token"]
        course_id = keys["course_id"]

        url = f"https://canvas.ucsc.edu/api/v1/courses/{course_id}/"
        endpoint = "users"
        headers = {"Authorization": f"Bearer {token}"}

        staff_json = []
        students_json = []

        params = {
            "enrollment_type[]": "teacher",
            "per_page": 1000,
        }

        staff_count = 0

        response = requests.request(
            "GET", url + endpoint, headers=headers, params=params
        )
        staff_json = response.json()
        print(f"Successfully retrieved staff data part {staff_count} from Canvas")
        while "next" in response.links:
            response = requests.request(
                "GET", response.links["next"]["url"], headers=headers
            )
            staff_json += response.json()
            staff_count += 1
            print(f"Successfully retrieved staff data part {staff_count} from Canvas")

        params = {
            "enrollment_type[]": "ta",
            "per_page": 1000,
        }

        response = requests.request(
            "GET", url + endpoint, headers=headers, params=params
        )
        staff_json += response.json()
        if len(response.json()) > 0:
            staff_count += 1
            print(f"Successfully retrieved staff data part {staff_count} from Canvas")
        while "next" in response.links:
            response = requests.request(
                "GET", response.links["next"]["url"], headers=headers
            )
            staff_json += response.json()
            staff_count += 1
            print(f"Successfully retrieved staff data part {staff_count} from Canvas")

        params = {
            "enrollment_type[]": "student",
            "per_page": 1000,
        }

        student_count = 0

        response = requests.request(
            "GET", url + endpoint, headers=headers, params=params
        )
        students_json = response.json()
        print(f"Successfully retrieved student data part {student_count} from Canvas")
        while "next" in response.links:
            response = requests.request(
                "GET", response.links["next"]["url"], headers=headers
            )
            students_json += response.json()
            student_count += 1
            print(
                f"Successfully retrieved student data part {student_count} from Canvas"
            )

        print("Successfully retrieved all staff and student data from Canvas")

        staff = []
        for s in staff_json:
            if "login_id" not in s or "ucsc.edu" not in s["login_id"]:
                continue

            cruzid = s["login_id"].split("@ucsc.edu")[0]

            if cruzid in staff:
                continue

            if not sheet.is_staff(cruzid=cruzid):
                sn = s["sortable_name"].split(", ")
                uid = None

                if sheet.student_exists(cruzid):
                    uid = sheet.get_uid(cruzid)
                    sheet.remove_student(cruzid)

                sheet.new_staff(sn[1], sn[0], cruzid, uid)

            staff.append(cruzid)

        sheet.clamp_staff(staff)

        print("Successfully processed staff data")

        students = {}
        for s in students_json:
            if "login_id" not in s or "ucsc.edu" not in s["login_id"]:
                continue

            cruzid = s["login_id"].split("@ucsc.edu")[0]

            if cruzid in students or cruzid in staff:
                print(f"Skipping {cruzid}")
                continue

            if not sheet.student_exists(cruzid):
                sn = s["sortable_name"].split(", ")
                students[cruzid] = s["id"]

                sheet.new_student(sn[1], sn[0], cruzid, s["id"], None)

            students[cruzid] = s["id"]

        sheet.clamp_students(students.keys())

        print("Successfully processed student data")

        endpoint = "modules"

        num_modules = -1

        for i, cruzid in enumerate(students):
            data = {"student_id": students[cruzid]}
            params = {"per_page": 1000}
            response = requests.request(
                "GET", url + endpoint, headers=headers, data=data, params=params
            )
            modules_json = json.loads(response.text)

            if num_modules == -1:
                num_modules = len(modules_json)

            completed_modules = []
            for m in modules_json:
                if m["state"] == "completed":
                    completed_modules.append(int(m["position"]))

            sheet.evaluate_modules(
                completed_modules, cruzid=cruzid, num_modules=num_modules
            )
            print(
                f"Successfully evaluated modules for {cruzid}, ({i+1}/{len(students)})"
            )

        print("\nSuccessfully evaluated modules for all students")

        if sheet.write_student_sheet():
            print("Successfully wrote student sheet")
        else:
            print("Failed to write student sheet")
            return False

        if sheet.write_staff_sheet():
            print("Successfully wrote staff sheet")
        else:
            print("Failed to write staff sheet")
            return False

        if sheet.log("Canvas Update", "", False, 0):
            print("Successfully logged canvas update")
        else:
            print("Failed to log canvas update")
            return False

        return True
    except KeyboardInterrupt:
        print("Exiting...")
        sheet.set_canvas_status_sheet(False)
        exit(0)


CANVAS_UPDATE_HOUR = 4  # 4am
CHECKIN_TIMEOUT = 5  # 5 minutes

if __name__ == "__main__":
    try:
        while True:
            sheet.get_canvas_status_sheet()
            if (
                sheet.canvas_needs_update
                or not sheet.last_canvas_update_time
                or (
                    (
                        datetime.now().date() > sheet.last_canvas_update_time.date()
                        and datetime.now().hour >= CANVAS_UPDATE_HOUR
                    )
                )
            ):
                print("Canvas update...")
                sheet.set_canvas_status_sheet(True)
                tmp_time = datetime.now()
                update()
                sheet.get_sheet_data()
                sheet.check_in()
                sheet.set_canvas_status_sheet(False, tmp_time)
            elif (
                not sheet.last_checkin_time
                or datetime.now() - sheet.last_checkin_time
                > timedelta(0, 0, 0, 0, CHECKIN_TIMEOUT, 0, 0)
            ):
                print("Checking in...")
                sheet.check_in()
            else:
                print("Waiting for next update...")
            time.sleep(60)
    except KeyboardInterrupt:
        print("Exiting...")
        sheet.set_canvas_status_sheet(False)
        exit(0)
