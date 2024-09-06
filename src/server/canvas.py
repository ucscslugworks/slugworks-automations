import json
import os

from canvasapi import Canvas

from .. import log
from . import server

# TODO: remove
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
    json.load(open("src/server/canvas_token.json"))["token"],
)
course = canvas.get_course(server.get_canvas_course_id())


def update():
    # Set Canvas status to "updating"
    server.set_canvas_status(server.CANVAS_UPDATING)

    # Get all staff members in the course (paginated list)
    staff = course.get_users(enrollment_type=["teacher", "ta", "designer"])

    # Empty list for all staff cruzids
    staff_done = []

    # Iterate through all staff members (as User objects)
    for s in staff:
        logger.debug(f"Starting staff {str(s)}")

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
    students = course.get_users(enrollment_type=["student"])

    # Empty list for all students cruzids
    students_done = []

    # Iterate through all students (as User objects)
    for s in students:
        logger.debug(f"Starting student {str(s)}")

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
    server.set_canvas_status(server.CANVAS_OK)

    # log completion message
    logger.info("Canvas update complete")


if __name__ == "__main__":
    update()
    # user = None
    # for s in course.get_users(enrollment_type=["student"]):
    #     if s.name == "Heli Kadakia":
    #         user = s
    #         break
    # print(user.get_profile())
    # [print(m.state, m.position) for m in course.get_modules(student_id=user.id)]
