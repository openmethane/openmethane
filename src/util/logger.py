
import logging
import os

LOG_LEVEL = os.getenv("LOG_LEVEL", None)

log_level = logging.INFO
if LOG_LEVEL is not None:
    log_levels = logging.getLevelNamesMapping()
    if LOG_LEVEL in log_levels.keys():
        log_level = log_levels[LOG_LEVEL]
        logging.basicConfig(level=log_level)
    else:
        logging.warning(f"LOG_LEVEL={LOG_LEVEL} is not a valid log level, must be one of: {', '.join(log_levels.keys())}")

def get_logger(package_name: str) -> logging.Logger:
    logger = logging.getLogger(package_name)
    logger.setLevel(log_level)
    return logger