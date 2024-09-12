# Gunicorn configuration file
# https://docs.gunicorn.org/en/stable/configure.html#configuration-file
# https://docs.gunicorn.org/en/stable/settings.html
import multiprocessing
import os
from datetime import datetime

max_requests = 1000
max_requests_jitter = 50

# # Change directory to current file location
# path = os.path.dirname(os.path.abspath(__file__))
# os.chdir(path)

chdir = "../.."

# get date & datetime strings
now = datetime.now()

# Set log path using timestamp
log_path = f"logs/flask/{now.strftime("%Y-%m-%d")}/{now.strftime("%Y-%m-%d %H:%M:%S")}.log"
errorlog = log_path
accesslog = log_path

# don't use syslog
syslog = False

# set log level to debug - include all logs
loglevel = "debug"

# send any output to logs
capture_output = True

# set number of worker threads
workers = multiprocessing.cpu_count() * 2 + 1

# define Flask app path
wsgi_app = "app:app"

# 0.0.0.0 makes site available externally, and bind to port 80 (default http port)
bind = "0.0.0.0:80"

# run in background as daemon, rather than in foreground as shell process
daemon = True
