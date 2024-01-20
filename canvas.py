import json

import requests

import sheet


def main():
    sheet.get_sheet_data(False)
    print("Successfully retrieved sheet data")

    keys = json.load(open("keys.json"))

    token = keys["canvas_auth_token"]
    course_id = keys["canvas_course_id"]

    url = f"https://canvas.ucsc.edu/api/v1/courses/{course_id}/"
    endpoint = "students"
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.request("GET", url + endpoint, headers=headers)

    students_json = json.loads(response.text)
    students = {}
    for s in students_json:
        # TODO: check if student is a staff member, and if so, skip them
        if "ucsc.edu" not in s["login_id"] or s["login_id"] in students:
            continue

        cruzid = s["login_id"].split("@ucsc.edu")[0]
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

    sheet.write_student_sheet()

    print("Successfully wrote student sheet")


if __name__ == "__main__":
    main()
