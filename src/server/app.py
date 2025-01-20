import logging
import os
import sqlite3

from flask import Flask
from flask_login import LoginManager

from src.server.auth_db import init_db_command
from src.server.auth_user import User


def create_app():
    logger = logging.getLogger("gunicorn.error")

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
