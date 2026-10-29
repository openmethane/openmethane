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

import openmethane.fourdvar.util.date_handle as dt
import openmethane.fourdvar.util.file_handle as fh
import openmethane.fourdvar.util.netcdf_handle as ncf
from openmethane import bcon_map
from openmethane.fourdvar.datadef.abstract._physical_abstract_data import (
    BCON_UNITS,
    set_step_units,
)
from openmethane.fourdvar.params import (
    cmaq_config,
    date_defn,
    input_defn,
    template_defn,
)
from openmethane.fourdvar.uncertainty import convert_unc


def load_bcon_map(save_path: str):
    """
    Read the boundary map, building it first if BCON_MAP_FILE is not set

    A map built here is written next to the prior as `bcon_map.nc`, so the
    regions behind a prior can always be looked up. Returns the region map, the
    step boundaries (seconds from START_DATE) and the uncertainty (ppm).
    """
    start, end = date_defn.start_date, date_defn.end_date
    bcon_file = dt.replace_date(cmaq_config.bcon_file, start)
    map_file = input_defn.bcon_map_file
    if map_file is None:
        map_file = os.path.join(os.path.dirname(save_path), "bcon_map.nc")
        if os.path.exists(map_file):
            print(
                f"WARNING: BCON_MAP_FILE is not set, so the existing boundary map\n"
                f"  {map_file}\n"
                "is being replaced by a newly built one. Any edits to it are lost; set "
                "BCON_MAP_FILE to use an edited map."
            )
        ds = bcon_map.build_bcon_map(
            bcon_file,
            start,
            end,
            segment_km=input_defn.bcon_segment_km,
            step_days=input_defn.bcon_step_days,
            nbands=input_defn.bcon_nbands,
            remainder=input_defn.bcon_remainder,
            unc=input_defn.bcon_unc,
        )
        ds.to_netcdf(map_file)
        print(f"Boundary map built and saved to:\n  {map_file}")

    region_map, step_start, step_end, unc = bcon_map.read_bcon_map(map_file, start, end)
    bcon_map.validate_map(
        region_map,
        step_start,
        step_end,
        unc,
        run_seconds=len(dt.get_datelist()) * 24 * 60 * 60,
        nlays=int(ncf.get_attr(bcon_file, "NLAYS")),
        ncols=int(ncf.get_attr(bcon_file, "NCOLS")),
        nrows=int(ncf.get_attr(bcon_file, "NROWS")),
    )
    # a hand-edited map can put a step edge inside a day of a time-independent BCON
    if bcon_map.file_record_seconds(bcon_file, start) is None:
        bcon_map.check_steps_at_midnight(step_start, step_end)
    return region_map, step_start, step_end, unc


def make_prior(save_path: str, emis_template: str) -> None:
    """
    Create a dataset containing the initial assumption about emissions

    Parameters
    ----------
    save_path
        Where to save the output file

    emis_template
        Template path for the emissions file.

        Must have been generated with make_emis_template before running this function.
    """
    fh.ensure_path(os.path.dirname(save_path))

    # spcs used in PhysicalData
    # list of spcs (eg: ['CO2','CH4','CO']) OR 'all' to use all possible spcs
    spc_list = ["CH4"]

    # number of layers for PhysicalData emissions (fluxes)
    # int for custom layers or 'all' to use all possible layers
    emis_nlay = 1

    # No. days per PhysicalData diurnal timestep
    # possible values:
    # 'single' for using a single average across the entire model run
    # integer to use custom number of days
    tday = "single"

    # data for emission uncertainty
    # allowed values:
    # single number: apply value to every uncertainty
    # dict: apply single value to each spcs ( eg: { 'CO2':1e-6, 'CO':1e-7 } )
    # string: filename for netCDF file already correctly formatted.
    # emis_unc = 1e-8 # mol/(s*m**2)
    emis_unc = 0.6  # unitless emissions multiplier

    # data for ICON scaling
    # list of values, one for each species
    icon_scale = [1.0]
    # icon_unc = [0.01]
    # icon_unc = [5e-3]
    icon_unc = [5 * 10e-3]
    # boundary condition offsets (ppm), added to the staged BCON. Their regions,
    # time steps and uncertainty come from the boundary map file (BCON_MAP_FILE),
    # or are built from the BCON_* settings, see make_bcon_map.py.
    region_map, step_start, step_end, bcon_unc = load_bcon_map(save_path)

    # convert spc_list into valid list
    emissions_filename = dt.replace_date(emis_template, date_defn.start_date)
    var_list = ncf.get_attr(emissions_filename, "VAR-LIST").split()
    if input_defn.inc_icon is True:
        ifile = dt.replace_date(cmaq_config.icon_file, date_defn.start_date)
        i_var_list = ncf.get_attr(ifile, "VAR-LIST").split()
        var_list = list(set(var_list).intersection(set(i_var_list)))
    if str(spc_list).lower() == "all":
        spc_list = [v for v in var_list]
    else:
        try:
            assert set(spc_list).issubset(set(var_list))
            spc_list = [s for s in spc_list]
        except AssertionError:
            print("spc_list must be a subset of cmaq spcs")
            raise
        except:
            print("invalid spc_list")
            raise

    # check that icon_scale & icon_unc are valid
    if input_defn.inc_icon is True:
        assert len(spc_list) == len(icon_scale), "Invalid icon_scale size"
        assert len(spc_list) == len(icon_unc), "Invalid icon_unc size"

    # convert emis_nlay into valid number
    enlay = int(ncf.get_attr(emissions_filename, "NLAYS"))
    if str(emis_nlay).lower() == "all":
        emis_nlay = enlay
    else:
        try:
            assert int(emis_nlay) == emis_nlay
            emis_nlay = int(emis_nlay)
        except:
            print("invalid emis_nlay")
            raise
        if emis_nlay > enlay:
            raise AssertionError(f"emis_nlay must be <= {enlay}")

    # convert tday into valid number of days
    if str(tday).lower() == "single":
        tday = len(dt.get_datelist())
    else:
        try:
            assert int(tday) == tday
            tday = int(tday)
        except:
            print("invalid tday")
            raise
    tot_nday = len(dt.get_datelist())
    assert tday <= tot_nday, "tday must be <= No. days in model run"
    assert tot_nday % tday == 0, "tday must cleanly divide No. days in model run"

    # emis-file timestep must fit into PhysicalData tstep
    estep = int(ncf.get_attr(emissions_filename, "TSTEP"))
    print("estep:", estep)

    emis_nstep = tot_nday // tday

    # convert emis-file data into needed PhysicalData format
    nrow = int(ncf.get_attr(emissions_filename, "NROWS"))
    ncol = int(ncf.get_attr(emissions_filename, "NCOLS"))

    # emis is scaling term, use to multiply a pre-defined daily pattern of emission values.
    # set prior value to 1. (no change from template).
    emis_dict = {}
    for spc in spc_list:
        emis_data = np.ones((emis_nstep, emis_nlay, nrow, ncol))
        emis_dict[spc] = emis_data

    emis_unc = convert_unc(emis_unc, emis_dict)
    emis_dict.update(emis_unc)

    # the staged BCON is the prior boundary condition, so the prior offset is 0
    bcon_regions = bcon_unc.shape[1]
    bcon_dict = {}
    for spc in spc_list:
        bcon_dict[spc] = np.zeros_like(bcon_unc)
        bcon_dict[f"{spc}_UNC"] = bcon_unc

    # build data into new netCDF file
    root_dim = {"ROW": nrow, "COL": ncol}
    root_attr = {
        "SDATE": np.int32(dt.replace_date("<YYYYDDD>", date_defn.start_date)),
        "EDATE": np.int32(dt.replace_date("<YYYYDDD>", date_defn.end_date)),
        #'TSTEP': [ np.int32( tstep[0] ), np.int32( tstep[1] ) ],
        "VAR-LIST": "".join([f"{s:<16}" for s in spc_list]),
    }

    root = ncf.create(path=save_path, attr=root_attr, dim=root_dim, is_root=True)

    emis_dim = {"TSTEP": None, "LAY": emis_nlay}
    emis_attr = {"TDAY": tday}
    emis_var = {k: ("f4", ("TSTEP", "LAY", "ROW", "COL"), v) for k, v in list(emis_dict.items())}
    ncf.create(parent=root, name="emis", dim=emis_dim, attr=emis_attr, var=emis_var, is_root=False)

    if input_defn.inc_icon is True:
        icon_dim = {"SPC": len(spc_list)}
        icon_var = {
            "ICON-SCALE": ("f4", ("SPC",), np.array(icon_scale)),
            "ICON-UNC": ("f4", ("SPC",), np.array(icon_unc)),
        }
        ncf.create(parent=root, name="icon", dim=icon_dim, var=icon_var, is_root=False)

    bcon_dim = {
        "TSTEP": None,
        "BCON": bcon_regions,
        "LAY": region_map.shape[0],
        "PERIM": region_map.shape[1],
    }
    bcon_attr = {"units": BCON_UNITS}

    bcon_var = {k: ("f4", ("TSTEP", "BCON"), v) for k, v in list(bcon_dict.items())}
    bcon_var["BCON_REGION"] = ("i4", ("LAY", "PERIM"), region_map)
    bcon_var["STEP_START"] = ("i8", ("TSTEP",), step_start)
    bcon_var["STEP_END"] = ("i8", ("TSTEP",), step_end)

    bcon_grp = ncf.create(
        parent=root, name="bcon", dim=bcon_dim, attr=bcon_attr, var=bcon_var, is_root=False
    )
    set_step_units(bcon_grp)

    root.close()
    print(f"Prior created and save to:\n  {save_path}")


if __name__ == "__main__":
    make_prior(save_path=input_defn.prior_file, emis_template=template_defn.emis)
