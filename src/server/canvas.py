import json
import os
import time
from datetime import datetime

from canvasapi import Canvas

from src import constants, log
from src.server import server

# TODO: remove (when the canvas course id is set in the UI)
server.set_canvas_course_id(67429)

# Change directory to repository root
path = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
os.chdir(path)

# Create a new logger for the canvas module
logger = log.setup_logs("canvas", log.INFO)

# Set up the canvas API client using a saved auth token
canvas = Canvas(
    "https://canvas.ucsc.edu",
    json.load(
        open(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..",
                "..",
                "common",
                "canvas.json",
            )
        )
    )["auth_token"],
)
course = canvas.get_course(server.get_canvas_course_id())


def update():
    # Set Canvas status to "updating"
    server.set_canvas_status(constants.CANVAS_UPDATING)

    # Get all staff members in the course (paginated list)
    staff = course.get_users(
        enrollment_type=["teacher", "ta", "designer"], enrollment_state=["active"]
    )

    # Empty list for all staff cruzids
    staff_done = []

    # length of staff list
    staff_len = 0
    for _ in staff:
        staff_len += 1

    # Iterate through all staff members (as User objects)
    for i, s in enumerate(staff):
        logger.debug(f"Starting staff {str(s)} ({i}/{staff_len})")

        # Get the user's profile
        profile = s.get_profile()

        # If the user does not have a login_id or is not a ucsc.edu email, skip
        if "login_id" not in profile or "ucsc.edu" not in profile["login_id"]:
            continue

        # Get the user's cruzid
        cruzid = profile["login_id"].split("@")[0]

        # If the user has already been processed, skip
        if cruzid in staff_done:
            continue

        # Get the user's first and last name
        lastname, firstname = tuple(profile["sortable_name"].split(", ", 1))

        # If the user is not already a staff member in the db, add them
        if not server.is_staff(cruzid):
            # UID variable for the staff member
            uid = None
            # If the user is currently a student
            if server.is_student(cruzid):
                # Get the student's UID
                uid = server.get_uid(cruzid)

            # Add the user as a staff member
            server.add_staff(cruzid, firstname, lastname, uid)

        # Add cruzid to list of completed staff members
        staff_done.append(cruzid)

        # Log the staff member's information
        logger.info(f"staff: {firstname} {lastname} ({cruzid})")

    # Log that the staff list has been updated
    logger.info("staff list updated")

    # get number of modules in the course
    num_modules = len(list(course.get_modules()))

    # Get all students in the course (paginated list)
    students = course.get_users(
        enrollment_type=["student"], enrollment_state=["active"]
    )

    # Empty list for all students cruzids
    students_done = []

    # length of students list
    students_len = 0
    for _ in students:
        students_len += 1

    # Iterate through all students (as User objects)
    for i, s in enumerate(students):
        logger.debug(f"Starting student {str(s)} ({i}/{students_len})")

        # Get the user's profile
        profile = s.get_profile()

        # If the user does not have a login_id or is not a ucsc.edu email, skip
        if "login_id" not in profile or "ucsc.edu" not in profile["login_id"]:
            continue

        # Get the user's cruzid
        cruzid = profile["login_id"].split("@")[0]

        # If the user has already been processed or is a staff member, skip
        if cruzid in students_done or cruzid in staff_done:
            continue

        # Get the user's first and last name
        lastname, firstname = tuple(profile["sortable_name"].split(", ", 1))

        # If the user is not already a student in the db, add them
        if not server.is_student(cruzid):
            # UID variable for the student
            uid = None
            # If the user is currently a staff member
            if server.is_staff(cruzid):
                # Get the staff member's UID
                uid = server.get_uid(cruzid)

            # Add the user as a student
            server.add_student(cruzid, firstname, lastname, uid)

        # Add cruzid to list of completed students
        students_done.append(cruzid)

        # Log the student's information
        logger.info(f"student: {firstname} {lastname} ({cruzid})")

        # List of completed modules for this student
        completed_modules = []

        # Iterate through all modules for this student
        for m in course.get_modules(student_id=s.id):
            # If the module is marked as done, add it to the list
            if m.state == "completed":
                completed_modules.append(int(m.position))

        # Evaluate the student's completed modules
        server.evaluate_modules(completed_modules, cruzid, num_modules)

        # Log the student's completed modules
        logger.info(f"student: {cruzid} completed modules: {completed_modules}")

    # Log that the student list has been updated
    logger.info("student list updated")

    # Clamp the staff and student lists to only include users that are in the course
    server.clamp_staff(staff_done)
    server.clamp_students(students_done)

    # Set Canvas status to "ok" (done)
    server.set_canvas_status(constants.CANVAS_OK)

    # log completion message
    logger.info("Canvas update complete")


def auto_updater():
    logger.info("Initialization complete")
    need_update = False
    # try/except to exit nicely if a keyboard interrupt is received
    try:
        # loop to continuously update Canvas data
        while True:
            # try/except to log error and continue if an error occurs - unless a keyboard interrupt is received
            try:
                # variable to allow for checking & logging separate conditions
                need_update = False
                # get current canvas status
                canvas_return = server.get_canvas_status()

                # if the return value is None, skip
                if canvas_return is None:
                    continue

                # unpack the return value
                status, last_update = canvas_return

                if status == constants.CANVAS_PENDING:
                    # if pending, user must have requested the update
                    need_update = True
                    logger.info("Canvas update requested by user")
                elif last_update == constants.NEVER:
                    # first run, updater has never run before
                    need_update = True
                    logger.info("Canvas update never done")
                elif (
                    datetime.fromtimestamp(last_update).date() < datetime.now().date()
                    and datetime.now().hour >= server.get_canvas_update_hour()
                ):
                    # last update's date was before today, and pre-set update hour is now or has passed
                    need_update = True
                    logger.info(
                        "Canvas update - last update was previous day & update hour is now/passed"
                    )

                if need_update:
                    # set update status to "UPDATING"
                    server.set_canvas_status(constants.CANVAS_UPDATING)
                    # save update start time - will be used for status
                    tmp_time = time.time()
                    # perform canvas update
                    update()
                    # set update status to ok/done
                    server.set_canvas_status(constants.CANVAS_OK, tmp_time)

                # sleep for 60 seconds - prevents spamming/overloading
                time.sleep(60)

            except Exception as e:
                # if an error occurs
                if type(e) == KeyboardInterrupt:  # if it's a keyboard interrupt, exit
                    raise e
                # otherwise, log the error, sleep for 60 seconds, and mark the canvas status as no longer updating
                logger.error(f"Error: {e}")
                time.sleep(60)
                server.set_canvas_status(constants.CANVAS_OK)

    except KeyboardInterrupt:
        # if error was a keyboard interrupt, log and exit
        print("Exiting...")
        # mark the canvas status as no longer updating
        server.set_canvas_status(constants.CANVAS_OK)
        exit(0)


if __name__ == "__main__":
    auto_updater()
