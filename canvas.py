import json
import logging
import os
import time
from datetime import datetime, timedelta

import requests

import sheet

# Change directory to current file location
path = os.path.dirname(os.path.abspath(__file__))
os.chdir(path)

# Create a new directory for logs if it doesn't exist
if not os.path.exists(path + "/logs/canvas"):
    os.makedirs(path + "/logs/canvas")

# create new logger with all levels
logger = logging.getLogger("root")
logger.setLevel(logging.DEBUG)

# create file handler which logs debug messages (and above - everything)
fh = logging.FileHandler(f"logs/canvas/{str(datetime.now())}.log")
fh.setLevel(logging.DEBUG)

# create console handler which only logs warnings (and above)
ch = logging.StreamHandler()
ch.setLevel(logging.WARNING)

# create formatter and add it to the handlers
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s: %(message)s")
fh.setFormatter(formatter)
ch.setFormatter(formatter)

# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)


# Function to list all modules in a course
def list_modules():
    # Load keys from json file
    keys = json.load(open("canvas.json"))

    # get Canvas API auth token and course ID
    token = keys["auth_token"]
    course_id = keys["course_id"]

    # Canvas API endpoint for modules & auth header
    url = f"https://canvas.ucsc.edu/api/v1/courses/{course_id}/modules"
    headers = {"Authorization": f"Bearer {token}"}

    # Parameters for the request (shouldn't need to apply since there aren't more than 1000 modules)
    params = {
        "per_page": 1000,
    }

    # Send GET request to Canvas API, record response
    response = requests.request("GET", url, headers=headers, params=params)

    # Print the response in a pretty format
    print(json.dumps(response.json(), indent=4))


# Function to perform a full Canvas update (pull all staff and student data, evaluate modules, and write to sheets)
def update():
    # try/except to exit nicely if a keyboard interrupt is received
    try:
        # Get the current sheet data
        sheet.get_sheet_data(limited=False)
        logger.info("Successfully retrieved sheet data")

        # Load keys from json file
        keys = json.load(open("canvas.json"))

        # get Canvas API auth token and course ID
        token = keys["auth_token"]
        course_id = keys["course_id"]

        # Canvas API endpoint root & auth header
        url = f"https://canvas.ucsc.edu/api/v1/courses/{course_id}/"
        headers = {"Authorization": f"Bearer {token}"}

        # specify users endpoint
        endpoint = "users"

        # Initialize lists for staff and students
        staff_json = []
        students_json = []

        # Parameters for the request - search only for Teachers
        params = {
            "enrollment_type[]": "teacher",
            "per_page": 1000,
        }

        # counter to keep track of & print how many requests are made
        staff_count = 0

        # make initial request to Canvas API for teacher data
        response = requests.request(
            "GET", url + endpoint, headers=headers, params=params
        )

        # convert response to json and add to staff_json list
        staff_json = response.json()

        # log success & counter
        logger.info(f"Successfully retrieved staff data part {staff_count} from Canvas")

        # while there are more pages of teacher data to retrieve
        while "next" in response.links:
            # make request for next page of teacher data
            response = requests.request(
                "GET", response.links["next"]["url"], headers=headers
            )
            # convert response to json and add to staff_json list
            staff_json += response.json()
            # increment counter
            staff_count += 1
            # log success & counter
            logger.info(
                f"Successfully retrieved staff data part {staff_count} from Canvas"
            )

        # Parameters for the request - search only for TAs
        params = {
            "enrollment_type[]": "ta",
            "per_page": 1000,
        }

        # make initial request to Canvas API for TA data
        response = requests.request(
            "GET", url + endpoint, headers=headers, params=params
        )
        # convert response to json and add to staff_json list
        staff_json += response.json()
        # if there was any data, increment counter and log success
        if len(response.json()) > 0:
            staff_count += 1
            logger.info(
                f"Successfully retrieved staff data part {staff_count} from Canvas"
            )

        # while there are more pages of TA data to retrieve
        while "next" in response.links:
            # make request for next page of TA data
            response = requests.request(
                "GET", response.links["next"]["url"], headers=headers
            )
            # convert response to json and add to staff_json list
            staff_json += response.json()
            # increment counter
            staff_count += 1
            # log success and counter
            logger.info(
                f"Successfully retrieved staff data part {staff_count} from Canvas"
            )

        # Parameters for the request - search only for Students
        params = {
            "enrollment_type[]": "student",
            "per_page": 1000,
        }

        # counter to keep track of & print how many requests are made
        student_count = 0

        # make initial request to Canvas API for student data
        response = requests.request(
            "GET", url + endpoint, headers=headers, params=params
        )
        # convert response to json and add to students_json list
        students_json = response.json()
        # log success & counter
        logger.info(
            f"Successfully retrieved student data part {student_count} from Canvas"
        )
        # while there are more pages of student data to retrieve
        while "next" in response.links:
            # make request for next page of student data
            response = requests.request(
                "GET", response.links["next"]["url"], headers=headers
            )
            # convert response to json and add to students_json list
            students_json += response.json()
            # increment counter
            student_count += 1
            # log success & counter
            logger.info(
                f"Successfully retrieved student data part {student_count} from Canvas"
            )

        # log success for all staff and student data
        logger.info("Successfully retrieved all staff and student data from Canvas")

        # parse staff data from json into list - indicates staff cruzids that have already been processed
        staff = []
        # for each staff member in the json
        for s in staff_json:
            # if there is no login_id or it is not a ucsc email, skip
            if "login_id" not in s or "ucsc.edu" not in s["login_id"]:
                continue

            # get cruzid from login_id
            cruzid = s["login_id"].split("@ucsc.edu")[0]

            # if the cruzid is already in staff (ex. user is both a teacher and a TA), skip
            if cruzid in staff:
                continue

            # if the cruzid is not staff in the sheet/database, add it
            if not sheet.is_staff(cruzid=cruzid):
                # split the sortable_name into first and last name
                sn = s["sortable_name"].split(", ")
                # initialize uid to None - have not yet assigned a card
                uid = None

                # if the user is already a student in the sheet/database
                if sheet.student_exists(cruzid):
                    # get the uid from the sheet/database (could be None)
                    uid = sheet.get_uid(cruzid)
                    # remove the user as a student from the sheet/database
                    sheet.remove_student(cruzid)

                # add the user as staff in the sheet/database, with the uid (could be None)
                sheet.new_staff(sn[1], sn[0], cruzid, uid)

            # add the cruzid to the staff list
            staff.append(cruzid)

        # clamp the staff list to the staff in the sheet/database - remove any staff from the sheet if they are not in the list
        sheet.clamp_staff(staff)

        # log success for staff data
        logger.info("Successfully processed staff data")

        # parse student data from json into dictionary - indicates student cruzids that have already been processed & their respective Canvas IDs
        students = {}
        # for each student in the json
        for s in students_json:
            # if there is no login_id or it is not a ucsc email, skip
            if "login_id" not in s or "ucsc.edu" not in s["login_id"]:
                continue

            # get cruzid from login_id
            cruzid = s["login_id"].split("@ucsc.edu")[0]

            # if the cruzid is already in students (ex. double listed across multiple sections) or is a staff member, skip
            if cruzid in students or cruzid in staff:
                logger.info(f"Skipping {cruzid}")
                continue

            # if the cruzid is not a student in the sheet/database, add it
            if not sheet.student_exists(cruzid):
                # split the sortable_name into first and last name
                sn = s["sortable_name"].split(", ")

                # add the user as a student in the sheet/database, with the Canvas ID
                sheet.new_student(sn[1], sn[0], cruzid, s["id"], None)

            # add the cruzid to the students dictionary with the Canvas ID
            students[cruzid] = s["id"]

        # clamp the students dictionary to the students in the sheet/database - remove any students from the sheet if they are not in the dictionary
        sheet.clamp_students(students.keys())

        # log success for student data
        logger.info("Successfully processed student data")

        # for each student, pull their module data and evaluate it to determine their accesses

        # specify modules endpoint
        endpoint = "modules"

        # initialize number of modules to -1
        num_modules = -1

        # for each student in the students dictionary
        for i, cruzid in enumerate(students):
            # data for the request - student_id is the Canvas ID
            data = {"student_id": students[cruzid]}
            # parameters for the request - set per_page to 1000 to get all modules (shouldn't need to apply since there aren't more than 1000 modules)
            params = {"per_page": 1000}
            # make request to Canvas API for module data
            response = requests.request(
                "GET", url + endpoint, headers=headers, data=data, params=params
            )
            # convert response to json
            modules_json = json.loads(response.text)

            # if num_modules is -1, set it to the length of the modules_json - indicates number of modules in the course (needed for evaluation)
            if num_modules == -1:
                num_modules = len(modules_json)

            # initialize list of completed modules
            completed_modules = []
            # for each module in the modules_json
            for m in modules_json:
                # if the module is completed, add its position (the module number) to the completed_modules list
                if m["state"] == "completed":
                    completed_modules.append(int(m["position"]))

            # evaluate the modules for the student given the completed_modules list and the number of modules
            sheet.evaluate_modules(
                completed_modules, cruzid=cruzid, num_modules=num_modules
            )

            # log success for the student
            logger.info(
                f"Successfully evaluated modules for {cruzid}, ({i+1}/{len(students)})"
            )

        # log success for all students
        logger.info("\nSuccessfully evaluated modules for all students")

        # attempt to write the student and staff sheets to Google Sheets, return errors if they fail
        if sheet.write_student_sheet():
            logger.info("Successfully wrote student sheet")
        else:
            logger.error("Failed to write student sheet")
            return False

        if sheet.write_staff_sheet():
            logger.info("Successfully wrote staff sheet")
        else:
            logger.error("Failed to write staff sheet")
            return False

        # log the canvas update
        if sheet.log("Canvas Update", "", False, 0):
            logger.info("Successfully logged canvas update")
        else:
            logger.error("Failed to log canvas update")
            return False

        return True
    # except to exit nicely if a keyboard interrupt is received
    except KeyboardInterrupt:
        print("Exiting...")
        sheet.set_canvas_status_sheet(False)
        exit(0)


# Constants
CANVAS_UPDATE_HOUR = 2  # update at 2am
CHECKIN_TIMEOUT = 5  # check in every 5 minutes

if __name__ == "__main__":
    # try/except to exit nicely if a keyboard interrupt is received
    try:
        # loop to continuously update Canvas data
        while True:
            # try/except to log error and continue if an error occurs - unless a keyboard interrupt is received
            try:
                # get the status of the canvas update
                sheet.get_canvas_status_sheet()

                if (
                    sheet.canvas_needs_update  # canvas needs an update
                    or not sheet.last_canvas_update_time  # or the last update time is None - first run
                    or (  # or it's a new day and past the update hour
                        (
                            datetime.now().date() > sheet.last_canvas_update_time.date()
                            and datetime.now().hour >= CANVAS_UPDATE_HOUR
                        )
                    )
                ):
                    logger.info("Canvas update...")
                    sheet.set_canvas_status_sheet(
                        True
                    )  # set the canvas updating status to True - currently in the process of updating (will prevent multiple updates at once and other devices from writing to the sheet)
                    tmp_time = (
                        datetime.now()
                    )  # store the time - indicates when the update started
                    update()  # perform the update
                    sheet.get_sheet_data(
                        limited=False
                    )  # get the updated sheet data (the data that was just written)
                    sheet.check_in()  # check in after the update
                    sheet.set_canvas_status_sheet(
                        False, tmp_time
                    )  # set the canvas updating status to False (indicates the update is complete) and store the time the update started
                elif (
                    not sheet.last_checkin_time # no checkin time recorded - has not checked in yet (first run)
                    or datetime.now() - sheet.last_checkin_time
                    > timedelta(0, 0, 0, 0, CHECKIN_TIMEOUT, 0, 0) # or it's been more than CHECKIN_TIMEOUT minutes since the last checkin
                ):
                    # log the checkin
                    logger.info("Checking in...")
                    # check in
                    sheet.check_in()
                else:
                    # log that it's waiting for the next update - indicates that it hasn't crashed yet
                    logger.info("Waiting for next update...")
                # sleep for 60 seconds - prevents the loop from running too quickly
                time.sleep(60)

            except Exception as e:
                # if an error occurs
                if type(e) == KeyboardInterrupt: # if it's a keyboard interrupt, exit
                    raise e
                # otherwise, log the error, sleep for 60 seconds, and mark the canvas status as no longer updating
                logger.error(f"Error: {e}")
                time.sleep(60)
                sheet.set_canvas_status_sheet(False)

    except KeyboardInterrupt:
        # if error was a keyboard interrupt, log and exit
        print("Exiting...")
        sheet.set_canvas_status_sheet(False)
        exit(0)
