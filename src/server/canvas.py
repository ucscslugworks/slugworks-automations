import json
import os
import time
from datetime import datetime

from canvasapi import Canvas

from src import canvas_util, constants, log
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


def split_name(profile: dict, cruzid: str):
    """Split a Canvas sortable_name ("Last, First") into first and last names."""
    sortable = (profile.get("sortable_name") or "").strip()
    if ", " in sortable:
        lastname, firstname = sortable.split(", ", 1)
        return firstname, lastname
    if sortable:
        # No comma to split on; keep the whole thing as the first name.
        return sortable, ""
    logger.warning(f"{cruzid} has no sortable_name in Canvas")
    return cruzid, ""


def resolve(s):
    """Resolve one Canvas user to an identity and their profile.

    Identity falls back through a ucsc.edu login_id, then the email, then
    sis_user_id - canvas_util lowercases the result and refuses a numeric SIS
    id, which is a student number rather than a CruzID.

    Returns (identity, profile), or (None, None) when Canvas gives us nothing
    usable to key on.
    """
    profile = s.get_profile()
    who = canvas_util.identity_of(profile, canvas)

    if not who.cruzid:
        logger.warning(
            f"skipping Canvas user {getattr(s, 'id', '?')}: no usable CruzID "
            f"(login_id={who.login_id!r}, sis_user_id={who.sis_user_id!r})"
        )
        return None, None

    if not who.login_id and who.sis_user_id:
        logger.info(f"{who.cruzid} identified by sis_user_id (no usable login_id)")

    return who, profile


def update():
    # Set Canvas status to "updating"
    server.set_canvas_status(constants.CANVAS_UPDATING)

    # Get all staff members in the course (as a list, so the paginated result
    # is fetched once rather than a second time just for the length)
    staff = list(
        course.get_users(
            enrollment_type=["teacher", "ta", "designer"], enrollment_state=["active"]
        )
    )

    # Empty list for all staff cruzids
    staff_done = []

    # Iterate through all staff members (as User objects)
    for i, s in enumerate(staff):
        logger.debug(f"Starting staff {str(s)} ({i}/{len(staff)})")

        # Resolve the user's identity, skipping anyone Canvas cannot key
        who, profile = resolve(s)
        if who is None:
            continue

        cruzid = who.cruzid

        # If the user has already been processed, skip
        if cruzid in staff_done:
            continue

        # If the user is not already a staff member in the db, add them
        if not server.is_staff(cruzid):
            # UID variable for the staff member
            uid = None
            # If the user is currently a student
            if server.is_student(cruzid):
                # Get the student's UID
                uid = server.get_uid(cruzid)

            # Get the user's first and last name
            firstname, lastname = split_name(profile, cruzid)

            # Add the user as a staff member
            server.add_staff(cruzid, firstname, lastname, uid)

        # Add cruzid to list of completed staff members
        staff_done.append(cruzid)

        # Log the staff member's information
        logger.info(f"staff: {cruzid}")

    # Log that the staff list has been updated
    logger.info("staff list updated")

    # get number of modules in the course
    num_modules = len(list(course.get_modules()))

    # Get all students in the course (as a list - see above)
    students = list(
        course.get_users(enrollment_type=["student"], enrollment_state=["active"])
    )

    # Empty list for all students cruzids
    students_done = []

    # Iterate through all students (as User objects)
    for i, s in enumerate(students):
        logger.debug(f"Starting student {str(s)} ({i}/{len(students)})")

        # Resolve the user's identity, skipping anyone Canvas cannot key
        who, profile = resolve(s)
        if who is None:
            continue

        cruzid = who.cruzid

        # If the user has already been processed or is a staff member, skip
        if cruzid in students_done or cruzid in staff_done:
            continue

        # If the user is not already a student in the db, add them
        if not server.is_student(cruzid):
            # UID variable for the student
            uid = None
            # If the user is currently a staff member
            if server.is_staff(cruzid):
                # Get the staff member's UID
                uid = server.get_uid(cruzid)

            # Get the user's first and last name
            firstname, lastname = split_name(profile, cruzid)

            # Add the user as a student
            server.add_student(cruzid, firstname, lastname, uid)

        # Add cruzid to list of completed students
        students_done.append(cruzid)

        # Log the student's information
        logger.info(f"student: {cruzid}")

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

    # Clamp the staff and student lists to only include users that are in the
    # course. Both lists hold normalized (lowercase) cruzids, matching what the
    # database stores - a case mismatch here would delete real users.
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
