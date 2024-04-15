import os
import json
import sqlite3
import time
from datetime import datetime, timedelta
from threading import Thread



from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from oauthlib.oauth2 import WebApplicationClient
import requests

# Internal imports
from db import init_db_command
from user import User
import canvas

# import control_nfc as nfc
import fake_nfc as nfc
import sheet

sheet.get_sheet_data()
# Open the file in write mode
with open('file.txt', 'w') as file:
    # Write the updated content to the file
    file.write('update=completed')