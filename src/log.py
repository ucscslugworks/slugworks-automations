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
        # Remove the latest.log symlink if it exists
        if os.path.exists(self.latest_filename):
            os.remove(self.latest_filename)

        # Create a new symlink to the latest log file
        os.symlink(str(filename) + ".log", self.latest_filename)

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
        os.symlink(nextName, self.latest_filename)


def setup_logs(name: str, level: int | None = None):

    if name in loggers:
        return loggers[name]

    # Change directory to repository root
    path = os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", name)
    )

    timestamp = datetime.datetime.now()
    folder = timestamp.strftime("%Y-%m-%d")
    filename = timestamp.strftime("%Y-%m-%d %H:%M:%S")

    # Create a new directory for logs if it doesn't exist
    if not os.path.exists(os.path.join(path, folder)):
        os.makedirs(os.path.join(path, folder))

    # create new logger with all levels
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    print(os.path.join(path, folder, filename))

    # create file handler which logs debug messages (and above - everything)
    fh = RollingFileHandler(
        os.path.join(path, folder, filename),
        os.path.join(path, "latest.log"),
        maxBytes=10 * 1000 * 1000,  # max log file size of 10MB
    )
    fh.setLevel(level if level else logging.INFO)

    # create console handler which only logs warnings (and above)
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)

    # create formatter and add it to the handlers
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s: %(message)s")
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)

    loggers[name] = logger

    return logger


setup_logs("root", DEBUG)
