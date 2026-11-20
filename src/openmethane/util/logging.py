"""Configure logging for a command-line entry point.

Modules log through `logging.getLogger(__name__)` and never configure logging
themselves. The entry point calls `configure_logging` once, before doing any
work, so importing a module has no effect on where or how much is logged.
"""

import logging
import os

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: str | int | None = None) -> None:
    """
    Send log records at or above a level to stderr.

    Replaces any handlers already on the root logger, so calling it again
    reconfigures logging rather than duplicating every line.

    Parameters
    ----------
    level
        A level name such as "DEBUG", or a level number. Defaults to the
        `LOG_LEVEL` environment variable, read when this is called, and then
        to "INFO".

    Raises
    ------
    ValueError
        If the level name is not one the logging module knows.
    """
    if level is None:
        level = os.environ.get("LOG_LEVEL") or "INFO"

    if isinstance(level, str):
        levels = logging.getLevelNamesMapping()
        if level.upper() not in levels:
            raise ValueError(f"Unknown log level {level!r}, expected one of: {', '.join(levels)}")
        level = levels[level.upper()]

    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)
