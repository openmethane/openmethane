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

from openmethane.fourdvar.env import env
from openmethane.fourdvar.params.root_path_defn import store_path

# Settings for archive processes

# location of archive directory
archive_path = os.path.join(store_path, "archive")

# archive model output of each successful iteration
iter_model_output = True

# archive observation-lite of each successful iteration
iter_obs_lite = True

# experiment name, used as the prefix of the directory each run saves results in:
# <experiment>-<YYYYMMDD>-<HHMMSS>, with <experiment>-latest linked to the newest
experiment = env.str("EXPERIMENT", "openmethane")

# description is copied into a txt file in the experiment directory
description = """This is a test of the fourdvar system.
The description here should contain details of the experiment
and is written to the description text file."""
# name of txt file holding the description, if empty string ('') file is not created.
desc_name = ""

# cmaq datadef files can be archived. These require an archive name pattern
# patterns can include <YYYYMMDD>, <YYYYDDD> or <YYYY-MM-DD> tags to specify day
# initial conditions file
icon_file = "icon.nc"
# emission file, requires a tag to map date
emis_file = "emis.<YYYYMMDD>.nc"
# concentration file, requires a tag to map date
conc_file = "conc.<YYYYMMDD>.nc"
# adjoint forcing file, requires a tag to map date
force_file = "force.<YYYYMMDD>.nc"
# concentration sensitivity file, requires a tag to map date
sens_conc_file = "sens_conc.<YYYYMMDD>.nc"
# emission sensitivity file, requires a tag to map date
sens_emis_file = "sens_emis.<YYYYMMDD>.nc"
