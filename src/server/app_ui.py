from flask import Blueprint

ui = Blueprint("ui", __name__)

# TODO: need to set up the ui pages


# main dashboard page
@ui.route("/")
def dashboard():
    return "dashboard"


# new user page
@ui.route("/new")
def new():
    return "new"


# edit user page
@ui.route("/edit")
def edit():
    return "edit"


# identify user page
@ui.route("/identify")
def identify():
    return "identify"
