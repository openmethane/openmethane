#
# Copyright 2016 University of Melbourne.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging
import os

from fourdvar.params.root_path_defn import root_path, store_path


def setup_logging(verbose: bool = False, reset_logfile: bool = True):
    """
    Setup logging for the project.

    The `OM_LOGGING_FILE` environment variable can be set to specify the name of the log file.
    This file will be created in the `store_path` directory.

    Parameters
    ----------
    verbose
        If True, set file logging level to DEBUG, otherwise set to INFO.
    reset_logfile
        If True, delete the log file if it already exists.
    """
    to_screen_level = logging.INFO
    to_file_level = logging.DEBUG if verbose else logging.INFO

    # format strings:
    to_screen_format = "%(name)s - %(levelname)s - %(message)s"
    # to_file_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    to_file_format = "%(name)s - %(levelname)s - %(message)s"

    project_name = os.path.split(root_path)[1]

    base_logger = logging.getLogger(project_name)
    base_logger.setLevel(logging.DEBUG)

    to_screen_handle = logging.StreamHandler()
    to_screen_handle.setLevel(to_screen_level)
    to_screen_formatter = logging.Formatter(to_screen_format)
    to_screen_handle.setFormatter(to_screen_formatter)
    base_logger.addHandler(to_screen_handle)

    if os.environ.get("OM_LOGGING_FILE"):
        logfile_name = os.environ.get("OM_LOGGING_FILE")
        logfile = os.path.join(store_path, logfile_name)

        if reset_logfile is True and os.path.isfile(logfile):
            os.remove(logfile)

        to_file_handle = logging.FileHandler(logfile)
        to_file_handle.setLevel(to_file_level)
        to_file_formatter = logging.Formatter(to_file_format)
        to_file_handle.setFormatter(to_file_formatter)
        base_logger.addHandler(to_file_handle)

    base_logger.debug("Logging setup finished.")


get_logger = logging.getLogger
