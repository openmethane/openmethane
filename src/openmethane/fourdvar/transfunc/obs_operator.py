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


import openmethane.fourdvar.util.netcdf_handle as ncf
from openmethane.fourdvar.datadef import ObservationData

ppm2ppb = 1e3
convFac = ppm2ppb


def obs_operator(model_output):
    """application: simulate set of observations from output of the forward model
    input: ModelOutputData
    output: ObservationData.
    """
    ObservationData.assert_params()

    # The operator is affine: the weight_grid carries the part of the column
    # that depends on the model state, and offset_term carries the rest (the
    # retrieval's (1 - A) * prior term, and whatever fills the column above the
    # model top). The offset belongs to the observation, not to any one day, so
    # it is added once here rather than inside the loop over dates.
    val_list = list(ObservationData.offset_term)
    for ymd, ilist in ObservationData.ind_by_date.items():
        conc_file = model_output.file_data["conc." + ymd]["actual"]
        var_dict = ncf.get_variable(conc_file, ObservationData.spcs)
        for i in ilist:
            for coord, weight in ObservationData.weight_grid[i].items():
                if str(coord[0]) == ymd:
                    step, lay, row, col, spc = coord[1:]
                    conc = var_dict[spc][step, lay, row, col]
                    val_list[i] += convFac * weight * conc

    return ObservationData(val_list)
