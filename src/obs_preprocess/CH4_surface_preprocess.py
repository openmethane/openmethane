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

import numpy as np
import pandas as pd

import fourdvar.util.file_handle as fh
from fourdvar.params import input_defn
from obs_preprocess.model_space import ModelSpace
from obs_preprocess.obs_defn import ObsSimple
from obs_preprocess.ray_trace import Point

# save new obs file as fourdvar input file
save_file = input_defn.obs_file
fh.ensure_path(os.path.dirname(save_file))


###this part is modified by NS:
ObsDir = "/home/563/sa6589/py4dvar/obs_preprocess/"
Obsfile = os.path.join(ObsDir, "May.csv")
obs_data = pd.read_csv(Obsfile, header=0)

date = obs_data["Date"]
obs_date = obs_data["Date"].tolist()
obs_timestep = obs_data["timestep"].tolist()
obs_lay = obs_data["layer"].tolist()
obs_lat = obs_data["lat"].tolist()
obs_lon = obs_data["lon"].tolist()
obs_spec = obs_data["spec"].tolist()


print(date.size)

obs_info = np.empty(date.size, dtype=object)

for i in range(date.size):
    obs_info[i] = (obs_date[i], obs_timestep[i], obs_lay[i], obs_lat[i], obs_lon[i], obs_spec[i])

obs_coord = obs_info.tolist()

obs_val_ppb = obs_data["obs"].tolist()

obs_val = np.empty(date.size, dtype=object)
obs_unc = np.empty(date.size, dtype=object)


for i in range(date.size):
    obs_val[i] = obs_val_ppb[i] * 1e-3  ##convert to ppm
    obs_unc[i] = 0.01 * obs_val[i]
    ##obs_unc[i] = 0.01 ##ppm

obs_val = obs_val.tolist()
obs_unc = obs_unc.tolist()


# make obs file using above parameters & fourdvar-CMAQ model
model_grid = ModelSpace.create_from_fourdvar()
domain = model_grid.get_domain()
domain["is_lite"] = False
obslist = [domain]
i = 0

##print zip( obs_coord, obs_val, obs_unc )

for coord, val, unc in zip(obs_coord, obs_val, obs_unc):
    xy = model_grid.get_xy(coord[3], coord[4])  # Sougol
    xyz = (xy[0], xy[1], 0.0)
    xyzCell = model_grid.grid.get_cell(Point(xyz))
    coord = list(coord)
    coord[2] = xyzCell[2]  # layer
    coord[3] = xyzCell[0]  # row
    coord[4] = xyzCell[1]
    print(i)  ##to check the number of obs are correct

    obs = ObsSimple.create(coord, val, unc, domain)  # Sougol
    obs.model_process(model_grid)

    ##obsdict = obs.get_obsdict()
    obsdict = obs.out_dict

    obsdict["lite_coord"] = coord

    obslist.append(obsdict)
    i = i + 1

# obsdict['weight_grid'] = domain
# obslist.append( obsdict )
##pdb.set_trace()
fh.save_list(obslist, save_file)
print(f"observations saved to {save_file}")
