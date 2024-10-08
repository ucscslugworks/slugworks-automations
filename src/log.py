import datetime
import logging
from logging.handlers import RotatingFileHandler
import os

CRITICAL = logging.CRITICAL
FATAL = logging.FATAL
ERROR = logging.ERROR
WARNING = logging.WARNING
WARN = logging.WARN
INFO = logging.INFO
DEBUG = logging.DEBUG
NOTSET = logging.NOTSET


class RollingFileHandler(RotatingFileHandler):

    def __init__(
        self,
        filename,
        mode="a",
        maxBytes=0,
        backupCount=0,
        encoding=None,
        delay=False,
        errors=None,
    ):
        self.last_backup_num = 0
        self.orig_filename = filename
        super(RollingFileHandler, self).__init__(
            filename=filename + ".log",
            mode=mode,
            maxBytes=maxBytes,
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
        )

    # override
    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        self.last_backup_num += 1
        nextName = "%s.%d.log" % (self.orig_filename, self.last_backup_num)
        self.rotate(self.baseFilename, nextName)
        if not self.delay:
            self.stream = self._open()


def setup_logs(name: str, level: int | None = None):
    cwd = os.getcwd()

    # Change directory to repository root
    path = os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    )
    os.chdir(path)

    timestamp = datetime.datetime.now()

    # Create a new directory for logs if it doesn't exist
    if not os.path.exists(path + f"/logs/{name}/{timestamp.strftime('%Y-%m-%d')}"):
        os.makedirs(path + f"/logs/{name}/{timestamp.strftime('%Y-%m-%d')}")

    # create new logger with all levels
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # create file handler which logs debug messages (and above - everything)
    filename = f"logs/{name}/{timestamp.strftime('%Y-%m-%d')}/{timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
    fh = RollingFileHandler(
        filename,
        maxBytes=10 * 1000 * 1000,  # max log file size of 10MB
    )
    fh.setLevel(level if level else logging.INFO)

    os.symlink(filename, f"logs/{name}/latest.log")

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

    # Change directory back to original
    os.chdir(cwd)

    return logger


setup_logs("root", DEBUG)
