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

import openmethane.fourdvar.util.cmaq_handle as cmaq
import openmethane.fourdvar.util.date_handle as dt
import openmethane.fourdvar.util.file_handle as fh
import openmethane.fourdvar.util.netcdf_handle as ncf
from openmethane import bcon_map
from openmethane.fourdvar.datadef import ModelInputData
from openmethane.fourdvar.params import (
    cmaq_config,
    input_defn,
    template_defn,
)
from openmethane.fourdvar.util import bcon_offset


def prepare_model(physical_data):
    """application: change resolution/formatting of physical data for input in forward model
    input: PhysicalData
    output: ModelInputData.

    notes: PhysicalData.bcon is an offset (ppm) added to each day's staged BCON,
    see openmethane.bcon_map.
    """
    if input_defn.inc_icon is True:
        model_input_args = {"icon": {}}
        for spcs, icon_scale in physical_data.icon.items():
            icon_array = ncf.get_variable(template_defn.icon, spcs)
            # ModelInput adds array values to template, change icon_scale accordingly
            # model_input_args['icon'][spcs] = (icon_scale-1.)*icon_array
            model_input_args["icon"][spcs] = (icon_scale) * icon_array
    else:
        model_input_args = {}

    dlist = dt.get_datelist()
    nrow, ncol = physical_data.nrows, physical_data.ncols

    emis_pattern = "emis.<YYYYMMDD>"
    for i, date in enumerate(dlist):
        spcs_dict = {}
        estep = int(i // physical_data.tday_emis)
        emis_fname = dt.replace_date(template_defn.emis, date)
        for spcs_name in physical_data.spcs:
            emis_arr = ncf.get_variable(emis_fname, spcs_name)
            phys_arr = physical_data.emis[spcs_name][estep, ...].reshape((1, 1, nrow, ncol))
            # emis_arr[:,:nlay,:,:] *= phys_arr
            emis_arr *= phys_arr  # note implicit broadcasting to all levels and timesteps
            spcs_dict[physical_data.spcs[0]] = emis_arr  # Sougol

        emis_argname = dt.replace_date(emis_pattern, date)
        model_input_args[emis_argname] = spcs_dict

    # add the boundary offset to each day's staged BCON
    region_map = physical_data.bcon_region_map
    for date, ymd, base_fname in bcon_offset.base_bcon_files():
        bcon_offset.check_grid(base_fname, region_map)
        rec_step = bcon_offset.record_steps(
            base_fname, date, physical_data.bcon_step_start, physical_data.bcon_step_end
        )
        bcon_dict = {}
        for spc in physical_data.spcs:
            base = ncf.get_variable(base_fname, spc)
            offset = bcon_map.expand(physical_data.bcon[spc], region_map, rec_step)
            bcon_dict[spc] = base + offset
        model_input_args[f"bcon.{ymd}"] = bcon_dict

    fh.ensure_path(os.path.dirname(cmaq_config.bcon_run_file))

    # may want to remove this line in future.
    cmaq.wipeout_fwd()

    return ModelInputData.create_new(**model_input_args)
