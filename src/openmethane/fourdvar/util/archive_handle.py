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
import os
from datetime import UTC, datetime

from openmethane.fourdvar.params import archive_defn
from openmethane.util.logger import get_logger

logger = get_logger(__name__)

finished_setup = False
archive_path = ""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def latest_link_name() -> str:
    """Name of the symlink which points at the most recent run's archive."""
    return f"{archive_defn.experiment}-latest"


def setup():
    """Setup the archive/experiment directory.
    input: None
    output: None.

    notes: creates a new, empty, timestamped directory for storing data
    (<experiment>-<YYYYMMDD>-<HHMMSS>, in UTC) and points the relative symlink
    <experiment>-latest at it. Existing archives are never moved or modified.
    """
    global finished_setup
    global archive_path
    if finished_setup is True:
        logger.warning("archive setup called again. Ignoring")
        return None

    run_name = f"{archive_defn.experiment}-{_utcnow():%Y%m%d-%H%M%S}"
    path = os.path.join(archive_defn.archive_path, run_name)
    # fails rather than reusing a directory if two runs start in the same second
    os.makedirs(path)

    # replace the link atomically so readers never see it missing
    link = os.path.join(archive_defn.archive_path, latest_link_name())
    tmp_link = f"{link}.tmp"
    if os.path.lexists(tmp_link):
        os.remove(tmp_link)
    os.symlink(run_name, tmp_link)
    os.replace(tmp_link, link)
    logger.info(f"archiving to {path}, linked from {link}")

    archive_path = path
    if archive_defn.desc_name != "":
        # add description to archive as text file.
        with open(os.path.join(archive_path, archive_defn.desc_name), "w") as desc_file:
            desc_file.write(archive_defn.description)
    finished_setup = True


def get_archive_path():
    global archive_path
    global finished_setup
    if finished_setup is False:
        setup()
    return archive_path
