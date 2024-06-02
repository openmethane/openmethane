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
import glob

from obs_preprocess.obsOCO2_defn import ObsOCO2
from obs_preprocess.model_space import ModelSpace
from netCDF4 import Dataset
import fourdvar.util.file_handle as fh
from fourdvar.params.root_path_defn import share_path
import fourdvar.params.input_defn as input_defn

# -CONFIG-SETTINGS---------------------------------------------------------

#'filelist': source = list of OCO2-Lite files
#'directory': source = directory, use all files in source
#'pattern': source = file_pattern_string, use all files that match pattern
source_type = "directory"

source = os.path.join(share_path, "obs_oco2_data")

output_file = input_defn.obs_file

# --------------------------------------------------------------------------

model_grid = ModelSpace.create_from_fourdvar()

if source_type.lower() == "filelist":
    filelist = [os.path.realpath(f) for f in source]
elif source_type.lower() == "pattern":
    filelist = [os.path.realpath(f) for f in glob.glob(source)]
elif source_type.lower() == "directory":
    dirname = os.path.realpath(source)
    filelist = [
        os.path.join(dirname, f)
        for f in os.listdir(dirname)
        if os.path.isfile(os.path.join(dirname, f))
    ]
else:
    raise TypeError("source_type '{}' not supported".format(source_type))

root_var = [
    "sounding_id",
    "latitude",
    "longitude",
    "time",
    "solar_zenith_angle",
    "sensor_zenith_angle",
    "warn_level",
    "xco2",
    "xco2_uncertainty",
    "xco2_apriori",
    "pressure_levels",
    "co2_profile_apriori",
    "xco2_averaging_kernel",
    "pressure_weight",
]
sounding_var = ["solar_azimuth_angle", "sensor_azimuth_angle"]
obslist = []
for fname in filelist:
    print("read {}".format(fname))
    var_dict = {}
    with Dataset(fname, "r") as f:
        size = f.dimensions["sounding_id"].size
        for var in root_var:
            var_dict[var] = f.variables[var][:]
        for var in sounding_var:
            var_dict[var] = f.groups["Sounding"].variables[var][:]
    print("found {} soundings".format(size))

    for i in range(size):
        src_dict = {k: v[i] for k, v in var_dict.items()}
        obs = ObsOCO2.create(**src_dict)
        obs.interp_time = False
        obs.model_process(model_grid)
        if obs.valid is True:
            obslist.append(obs.get_obsdict())

if len(obslist) > 0:
    domain = model_grid.get_domain()
    domain["is_lite"] = False
    datalist = [domain] + obslist
    fh.save_list(datalist, output_file)
    print("recorded observations to {}".format(output_file))
else:
    print("No valid observations found, no output file generated.")
