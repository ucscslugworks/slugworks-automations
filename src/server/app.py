import logging
import os
import sqlite3
import ssl

from flask import Flask, session
from flask_login import LoginManager

from src import log
from src.server.auth_db import init_db_command
from src.server.auth_user import User


def create_app():
    # logger = logging.getLogger("gunicorn.error")
    logger = log.setup_logs("flask")

    app = Flask(__name__)
    app.secret_key = os.urandom(24).hex()
    app.url_map.strict_slashes = True

    login_manager = LoginManager()
    login_manager.init_app(app)

    try:
        init_db_command(app)
    except sqlite3.OperationalError:
        logger.info("Database already exists")
        pass

    @login_manager.user_loader
    def load_user(user_id):
        # logger.debug(f"user_id: {user_id}")
        # logger.debug(f"session: {session}")
        # print(f"session: {session}")
        if session:
            u = User.get(session["_user_id"])
            if u:
                logger.debug(f"logged in with session id")
                return u

        return User.get(user_id)

    # blueprint for auth routes in our app
    from src.server.app_auth import auth as auth_blueprint

    app.register_blueprint(auth_blueprint)

    # blueprints for non-auth parts of app
    from src.server.app_api import api as api_blueprint
    from src.server.app_ui import ui as ui_blueprint

    app.register_blueprint(api_blueprint)
    app.register_blueprint(ui_blueprint)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5001, debug=True, ssl_context="adhoc")
