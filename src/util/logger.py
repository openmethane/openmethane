
import logging
import os
import pathlib

from fourdvar.params.root_path_defn import store_path


LOG_LEVEL = os.getenv("LOG_LEVEL", None)
LOG_FILE = os.getenv("LOG_FILE", None)
OM_LOGGING_FILE = os.getenv("OM_LOGGING_FILE", None)

def _setup_logger():
    """
    Parses environment variables and sets up logging based on their values.

    LOG_LEVEL - must be a valid logging level from the builtin logging package.
      Sets the log level of the base logger and all logs accessed via get_logger.

    LOG_FILE - a filename where the logger should attempt to log. If a relative
      path is provided, it will attempt to append it to the STORE_PATH. If the
      provided filename already exists, it will attempt to move the existing
      file by prefixing the filename with `000`, `001`, etc.

    :return: (log_level, log_file_handler)
    """
    # Set a default log level based on the LOG_LEVEL environment var
    log_level = logging.INFO
    if LOG_LEVEL is not None:
        log_levels = logging.getLevelNamesMapping()
        if LOG_LEVEL in log_levels.keys():
            log_level = log_levels[LOG_LEVEL]
            logging.basicConfig(level=log_level)
        else:
            logging.warning(f"LOG_LEVEL={LOG_LEVEL} is not a valid log level, must be one of: {', '.join(log_levels.keys())}")

    # Log to a file if a filename is provided in the LOG_FILE environment var
    log_file = None
    if OM_LOGGING_FILE is not None:
        logging.warning("OM_LOGGING_FILE is deprecated, use LOG_FILE instead")
        log_file = OM_LOGGING_FILE
    if LOG_FILE is not None:
        log_file = LOG_FILE

    log_file_handler = None
    if log_file is not None:
        if not log_file.startswith("/"):
            log_file = os.path.join(store_path, log_file)

        # if a file already exists at that path, move it
        if os.path.isfile(log_file):
            file_dir = os.path.dirname(log_file)
            file_name = os.path.basename(log_file)
            rotation = 0
            rotate_log_name = pathlib.Path(file_dir, f"{'{:03d}'.format(rotation)}.{file_name}")
            while os.path.exists(rotate_log_name):
                rotation += 1
                rotate_log_name = pathlib.Path(file_dir, f"{'{:03d}'.format(rotation)}.{file_name}")
            os.rename(log_file, rotate_log_name)

        log_file_handler = logging.FileHandler(log_file)
        # to_file_handle.setLevel(to_file_level)
        # to_file_formatter = logging.Formatter(to_file_format)
        # to_file_handle.setFormatter(to_file_formatter)

    return log_level, log_file_handler

def get_logger(package_name: str) -> logging.Logger:
    log_level, log_file_handler = _setup_logger()

    logger = logging.getLogger(package_name)
    logger.setLevel(log_level)

    if log_file_handler is not None:
        logger.addHandler(log_file_handler)

    return logger