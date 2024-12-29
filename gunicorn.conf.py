# Gunicorn configuration file
# https://docs.gunicorn.org/en/stable/configure.html#configuration-file
# https://docs.gunicorn.org/en/stable/settings.html
import multiprocessing
import os

from src import log

max_requests = 1000
max_requests_jitter = 50

# Change directory to current file location
path = os.path.dirname(os.path.abspath(__file__))
os.chdir(path)

# Set log path using timestamp
log_path = log.get_log_path("ui")

errorlog = log_path
accesslog = log_path

# don't use syslog
syslog = False

# set log level to debug - include all logs
loglevel = "debug"

# send any output to logs
capture_output = True

# set number of worker threads
# workers = multiprocessing.cpu_count() * 2 + 1
workers = 1

# define Flask app path
wsgi_app = "src.bambu_printers.app:create_app()"

# 0.0.0.0 makes site available externally, and bind to port 80 (default http port)
# bind = "0.0.0.0:80"
bind = "0.0.0.0:5001"

# start gunicorn as a background process
# daemon = True

keyfile = os.path.join(path, "common", "private_key.pem")
certfile = os.path.join(path, "common", "certificate.pem")
