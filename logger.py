import logging
from logging import DEBUG, INFO

CONN = 5

logging.addLevelName(CONN, "CONN")

# Used https://stackoverflow.com/questions/2183233/how-to-add-a-custom
# -loglevel-to-pythons-logging-facility/ as a reference
def conn(self, msg, *args, **kwargs):
    if self.isEnabledFor(CONN):
        self.log(CONN, msg, *args, **kwargs)


setattr(logging.getLoggerClass(), "conn", conn)

logger = logging.getLogger()
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

logger.setLevel(logging.INFO)
