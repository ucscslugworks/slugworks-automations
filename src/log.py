import datetime
import logging
import os
from logging.handlers import RotatingFileHandler

CRITICAL = logging.CRITICAL
FATAL = logging.FATAL
ERROR = logging.ERROR
WARNING = logging.WARNING
WARN = logging.WARN
INFO = logging.INFO
DEBUG = logging.DEBUG
NOTSET = logging.NOTSET

loggers = {}
file_handlers = {}
root_done = False


class RollingFileHandler(RotatingFileHandler):

    def __init__(
        self,
        filename,
        latest_filename,
        mode="a",
        maxBytes=0,
        backupCount=0,
        encoding=None,
        delay=False,
        errors=None,
    ):
        self.last_backup_num = 0
        self.orig_filename = filename
        self.latest_filename = latest_filename
        super(RollingFileHandler, self).__init__(
            filename=str(filename) + ".log",
            mode=mode,
            maxBytes=maxBytes,
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
        )

        try:
            # Remove the latest.log symlink if it exists
            if os.path.exists(self.latest_filename):
                os.remove(self.latest_filename)

            # Create a new symlink to the latest log file
            os.symlink(str(filename) + ".log", self.latest_filename)
        except:
            pass

    # override
    def doRollover(self):
        if self.stream:
            self.stream.close()
        self.last_backup_num += 1
        nextName = "%s.%d.log" % (self.orig_filename, self.last_backup_num)
        self.rotate(self.baseFilename, nextName)
        if not self.delay:
            self.stream = self._open()

        # Remove the latest.log symlink if it exists
        if os.path.exists(self.latest_filename):
            os.remove(self.latest_filename)

        # Create a new symlink to the latest log file
        os.symlink(self.baseFilename, self.latest_filename)


def setup_logs(
    name: str,
    level: int = INFO,
    additional_handlers: list[tuple[str, int]] = [],
):
    global root_done

    if name in loggers:
        return loggers[name]

    if not root_done:
        root_done = True
        setup_logs("root", DEBUG)

    # Change directory to repository root
    logs_path = os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
    )

    timestamp = datetime.datetime.now()
    folder = timestamp.strftime("%Y-%m-%d")
    filename = timestamp.strftime("%Y-%m-%d %H:%M:%S")

    # create new logger with all levels
    logger = logging.getLogger(name)
    logger.setLevel(DEBUG)

    # create formatter
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s: %(message)s")

    # create list of handlers
    handlers = []

    additional_handlers.append((name, level))

    for h_name, h_level in additional_handlers:
        if h_name in file_handlers:
            handlers.append(file_handlers[h_name])
        else:
            # Create a new directory for file handler if it doesn't exist
            if not os.path.exists(os.path.join(logs_path, h_name, folder)):
                os.makedirs(os.path.join(logs_path, h_name, folder))

            # create file handler which logs debug messages (and above - everything)
            fh = RollingFileHandler(
                os.path.join(logs_path, h_name, folder, filename),
                os.path.join(logs_path, h_name, "latest.log"),
                maxBytes=10 * 1000 * 1000,  # max log file size of 10MB
            )
            # set the level of the file handler (info by default) and the formatter
            fh.setLevel(h_level)
            fh.setFormatter(formatter)
            # add the file handler to the list of handlers for this logger
            handlers.append(fh)
            # add the file handler to the list of additional handlers
            file_handlers[h_name] = fh

    # create console handler which only logs warnings (and above)
    ch = logging.StreamHandler()
    # set the level of the console handler (warnings and above) and the formatter
    ch.setLevel(WARNING)
    ch.setFormatter(formatter)
    # add the console handler to the list of handlers
    handlers.append(ch)

    for handler in handlers:
        # add the handlers to the logger
        logger.addHandler(handler)

    loggers[name] = logger

    return logger


def get_log_path(name: str):
    # Change directory to repository root
    logs_path = os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
    )

    timestamp = datetime.datetime.now()
    folder = timestamp.strftime("%Y-%m-%d")
    filename = timestamp.strftime("%Y-%m-%d %H:%M:%S")

    # Create a new directory for date if it doesn't exist
    if not os.path.exists(os.path.join(logs_path, name, folder)):
        os.makedirs(os.path.join(logs_path, name, folder))

    # check for and remove existing latest symlink
    if os.path.islink(os.path.join(logs_path, name, "latest.log")) or os.path.exists(
        os.path.join(logs_path, name, "latest.log")
    ):
        os.remove(os.path.join(logs_path, name, "latest.log"))

    # Create a new symlink to the latest log file
    os.symlink(
        os.path.join(logs_path, name, folder, filename + ".log"),
        os.path.join(logs_path, name, "latest.log"),
    )
    return os.path.join(logs_path, name, folder, filename + ".log")
