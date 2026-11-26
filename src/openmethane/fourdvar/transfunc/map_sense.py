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

import numpy as np

import openmethane.fourdvar.util.date_handle as dt
import openmethane.fourdvar.util.netcdf_handle as ncf
from openmethane import bcon_map
from openmethane.fourdvar.datadef import PhysicalAdjointData
from openmethane.fourdvar.params import (
    cmaq_config,
    input_defn,
    template_defn,
)
from openmethane.fourdvar.util import bcon_offset, icon_offset
from openmethane.fourdvar.util.cmaq_io_files import get_filedict

unit_key = "units.<YYYYMMDD>"
unit_convert_emis = None


def get_unit_convert_emis():
    """Get unit conversion dictionary for sensitivity to each days emissions.
    input: None
    output: dict ('units.<YYYYMMDD>': np.ndarray( shape_of( template_defn.sense_emis ) ).

    notes: SensitivityData.emis units = CF/(ppm/s)
           PhysicalAdjointData.emis units = CF/(mol/s)
    """
    global unit_key

    # physical constants:
    # molar weight of dry air (precision matches cmaq)
    mwair = 28.9628
    # convert proportion to ppm
    ppm_scale = 1e6
    # convert g to kg
    kg_scale = 1e-3

    unit_dict = {}
    # all spcs have same shape, get from 1st
    tmp_spc = ncf.get_attr(template_defn.sense_emis, "VAR-LIST").split()[0]
    target_shape = ncf.get_variable(template_defn.sense_emis, tmp_spc)[:].shape
    # layer thickness constant between files
    lay_sigma = list(ncf.get_attr(template_defn.sense_emis, "VGLVLS"))
    # layer thickness measured in scaled pressure units
    lay_thick = [lay_sigma[i] - lay_sigma[i + 1] for i in range(len(lay_sigma) - 1)]
    lay_thick = np.array(lay_thick).reshape((1, len(lay_thick), 1, 1))

    for date in dt.get_datelist():
        met_file = dt.replace_date(cmaq_config.met_cro_3d, date)
        # slice off any extra layers above area of interest
        rhoj = ncf.get_variable(met_file, "DENSA_J")[:, : len(lay_thick), ...]
        xcell = ncf.get_attr(met_file, "XCELL")
        ycell = ncf.get_attr(met_file, "YCELL")
        cell_area = float(xcell * ycell)

        # assert timesteps are compatible
        assert (target_shape[0] - 1) >= (rhoj.shape[0] - 1), "incompatible timesteps"
        assert (target_shape[0] - 1) % (rhoj.shape[0] - 1) == 0, "incompatible timesteps"
        reps = (target_shape[0] - 1) // (rhoj.shape[0] - 1)

        rhoj_interp = np.zeros(target_shape)
        for r in range(reps):
            frac = float(2 * r + 1) / float(2 * reps)
            rhoj_interp[r:-1:reps, ...] = (1 - frac) * rhoj[:-1, ...] + frac * rhoj[1:, ...]
        rhoj_interp[-1, ...] = rhoj[-1, ...]
        unit_array = (ppm_scale * kg_scale * mwair) / (rhoj_interp * lay_thick) / cell_area

        day_label = dt.replace_date(unit_key, date)
        unit_dict[day_label] = unit_array
    return unit_dict


def map_sense(sensitivity):
    """application: map adjoint sensitivities to physical grid of unknowns.
    input: SensitivityData
    output: PhysicalAdjointData.
    """
    global unit_key
    global unit_convert_emis
    if unit_convert_emis is None:
        unit_convert_emis = get_unit_convert_emis()

    # check that:
    # - date_handle dates exist
    # - PhysicalAdjointData params exist
    # - template_defn.emis & template_defn.sense_emis are compatible
    # - the staged ICON & the conc sensitivity are compatible
    datelist = dt.get_datelist()
    PhysicalAdjointData.assert_params()

    # create blank constructors for PhysicalAdjointData
    p = PhysicalAdjointData
    if input_defn.inc_icon is True:
        icon_dict = {spc: 0.0 for spc in p.spcs}
    emis_shape = (
        p.nstep_emis,
        p.nlays_emis,
        p.nrows,
        p.ncols,
    )
    emis_dict = {spc: np.zeros(emis_shape) for spc in p.spcs}
    bcon_shape = (
        p.nstep_bcon,
        p.bcon_region,
    )
    bcon_dict = {spc: np.zeros(bcon_shape) for spc in p.spcs}
    del p

    # record 0 of the first day is the initial time: the adjoint of adding the
    # offset to every cell of ICON in prepare_model is the sum over that record
    # of ADJ_LGRID and of the forcing on the first CONC record, which ADJ_LGRID
    # leaves out (see util.icon_offset)
    if input_defn.inc_icon is True:
        ymd = dt.replace_date("<YYYYMMDD>", datelist[0])
        i_sense_fname = sensitivity.file_data[f"conc.{ymd}"]["actual"]
        i_force_fname = get_filedict("AdjointForcingData")[f"force.{ymd}"]["actual"]
        i_sense_vars = ncf.get_variable(i_sense_fname, icon_dict.keys())
        i_force_vars = ncf.get_variable(i_force_fname, icon_dict.keys())
        icon_vars = ncf.get_variable(icon_offset.base_icon_file(), icon_dict.keys())
        for spc in PhysicalAdjointData.spcs:
            sense_data = i_sense_vars[spc][0, ...]
            force_data = i_force_vars[spc][0, ...]
            msg = "conc_sense, force and the staged ICON are incompatible"
            assert sense_data.shape == force_data.shape == icon_vars[spc].shape[1:], msg
            icon_dict[spc] = icon_offset.apply_adjoint(sense_data, force_data)

    emis_pattern = "emis.<YYYYMMDD>"
    for i, date in enumerate(datelist):
        label = dt.replace_date(emis_pattern, date)
        sense_fname = sensitivity.file_data[label]["actual"]
        sense_data_dict = ncf.get_variable(sense_fname, PhysicalAdjointData.spcs)
        emis_fname = dt.replace_date(template_defn.emis, date)
        emis_vars = ncf.get_variable(emis_fname, emis_dict.keys())

        pstep = i // PhysicalAdjointData.tday_emis
        emis_unit = unit_convert_emis[dt.replace_date(unit_key, date)]
        for spc in PhysicalAdjointData.spcs:
            sense_arr_emis = sense_data_dict[spc]
            emis_dict[spc][pstep, :, :, :] += (sense_arr_emis * emis_vars[spc]).sum(
                axis=(0, 1)
            )  # reverses splattering over timesteps and layers in prepare-model

    # ADJ_LGRID_BC is the sensitivity to each BCON record and cell (CF/ppm), the
    # adjoint of adding the offset to BCON in prepare_model
    p = PhysicalAdjointData
    for ymd, _ in bcon_offset.base_bcon_files():
        sense_fname = sensitivity.file_data[f"bcon.{ymd}"]["actual"]
        bcon_offset.check_grid(sense_fname, p.bcon_region_map)
        rec_step = bcon_offset.record_steps(sense_fname, p.bcon_step_start, p.bcon_step_end)
        sense_vars = ncf.get_variable(sense_fname, p.spcs)
        for spc in p.spcs:
            bcon_dict[spc] += bcon_map.collapse(
                sense_vars[spc], p.bcon_region_map, rec_step, p.nstep_bcon, p.bcon_region
            )
    del p

    if input_defn.inc_icon is False:
        icon_dict = None
    return PhysicalAdjointData(icon_dict, emis_dict, bcon_dict)
