"""Shared logger and logging configuration for rsbt."""

import logging

logger = logging.getLogger("rsbt")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def configure_logging(debug=False):
    """(Re)configure the root logger's level and format.

    debug: when True, sets the level to DEBUG instead of INFO.
    """
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s", force=True)
