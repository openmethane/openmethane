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

# full path to the prior file used by user_driver.get_background
prior_file = os.path.join(store_path, "input/prior.nc")

# full path to the obs file used by user_driver.get_observed
obs_file = os.path.join(store_path, env.str("OBS_FILE_GLOB", "input/test_obs.pic.gz"))

# Solve for an offset (ppm) on the initial condition, added to the staged ICON
# of the first day. ICON_UNC is its prior 1-sigma uncertainty.
inc_icon = env.bool("INC_ICON", True)
icon_unc = env.float("ICON_UNC", 0.05)

# Boundary condition offsets (see openmethane.bcon_map and
# scripts/cmaq_preprocess/make_bcon_map.py). If BCON_MAP_FILE is unset,
# make_prior.py builds the map from the settings below.
bcon_map_file = env.str("BCON_MAP_FILE", "") or None
bcon_segment_km = env.float("BCON_SEGMENT_KM", 1000.0)
bcon_step_days = env.float("BCON_STEP_DAYS", 5.0)
bcon_nbands = env.int("BCON_NBANDS", 4)
bcon_remainder = env.str("BCON_REMAINDER", "spread")
# prior 1-sigma uncertainty of each boundary offset, in ppm
bcon_unc = env.float("BCON_UNC", 0.02)
