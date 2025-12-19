#!/usr/bin/env python
#
# Copyright 2023 The Superpower Institute Ltd
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
import datetime
from pathlib import Path
from typing import Any

import netCDF4 as nc
import numpy as np
from numpy.typing import NDArray

from openmethane.fourdvar.params import cmaq_config, template_defn
from openmethane.fourdvar.util.date_handle import replace_date

KG_TO_G = 1000.0  # conversion from kg to g
MOLAR_MASS_CH4 = 16.0  # molar mass of CH4
# attributes that CMAQ is expecting(1)
ATTR_NAMES = [
    "IOAPI_VERSION",
    "EXEC_ID",
    "FTYPE",
    "CDATE",
    "CTIME",
    "WDATE",
    "WTIME",
    "SDATE",
    "STIME",
    "TSTEP",
    "NTHIK",
    "NCOLS",
    "NROWS",
    "NLAYS",
    "NVARS",
    "GDTYP",
    "P_ALP",
    "P_BET",
    "P_GAM",
    "XCENT",
    "YCENT",
    "XORIG",
    "YORIG",
    "XCELL",
    "YCELL",
    "VGTYP",
    "VGTOP",
    "VGLVLS",
    "GDNAM",
    "UPNAM",
    "VAR-LIST",
    "FILEDESC",
]
N_LAYERS = 32
N_VARIABLES = 1
NZ = 32  # just surface for the moment


def read_metcro(
    met_cro_file: str, spec_list: list[str], expected_grid_shape: tuple[int, int]
) -> tuple[dict[str, int], dict[str, Any]]:
    """
    Read dimensions and attributes from the MCIP cross file
    """
    with nc.Dataset(met_cro_file, mode="r") as met_croNC:
        attrs = {}
        for a in ATTR_NAMES:
            val = met_croNC.getncattr(a)
            if a == "NVARS":
                attrs[a] = np.int32(len(spec_list))
            elif a == "VAR-LIST":
                var_string = "".join([f"{k:<16}" for k in spec_list])
                attrs[a] = var_string
            else:
                attrs[a] = val
        dimension_sizes = {"VAR": N_VARIABLES, "LAY": NZ, "TSTEP": 25, "DATE-TIME": 2}

        dom_shape = (met_croNC.NROWS, met_croNC.NCOLS)
        if dom_shape != expected_grid_shape:
            raise ValueError("incompatible dimensions in metcro and emissions")
        for k in met_croNC.dimensions.keys():
            dimension_sizes[k] = len(met_croNC.dimensions[k])
    # now correct a few of these
    dimension_sizes["VAR"] = N_VARIABLES
    dimension_sizes["LAY"] = NZ
    dimension_sizes["TSTEP"] = 25

    return dimension_sizes, attrs


def build_tflag_data(current: datetime.date, shape: tuple[int, int, int]) -> NDArray:
    """
    Build the contents of tflag

    tflag is a 3d array with the dimensions (TSTEPS, VARS, DATE-TIME).

    The datetime is represented using two parts (the last dimension),
    the first component is the date (YYYYDDD) and the second is the time (HHMM)
    """
    HOURS_IN_DAY = 24

    assert shape[0] == HOURS_IN_DAY + 1
    assert shape[-1] == 2

    times = np.zeros(shape, dtype=np.int32)

    # Date component of timestep
    # integer of form: YYYYDDD
    date_doy = current.timetuple().tm_yday
    times[:, :, 0] = 1000 * current.year + date_doy

    # need to set next day which requires care if it's Dec 31
    next = current + datetime.timedelta(1)  # add one day
    next_doy = next.timetuple().tm_yday
    times[-1, :, 0] = 1000 * next.year + next_doy  # setting date of last time-slice

    # hourly timestep including last timeslice to 0
    # integer of form: HHMM
    hours = (np.arange(shape[0]) % HOURS_IN_DAY) * 10000
    times[:, :, 1] = hours[:, np.newaxis]
    return times


def make_emissions_templates(prior_file: str, metcro_template: str, emis_template: str):
    """
    Create emissions template files for CMAQ using the OpenMethane prior data

    The emissions are read from the OpenMethane prior file
    and written to the CMAQ emissions template file,
    one file per day in the prior file.

    Parameters
    ----------
    prior_file
        Path to the OpenMethane prior file
    metcro_template
        Path to the CMAQ metcro template file

        This may contain a date placeholder that will be replaced with the date of the emissions
    emis_template
        Path to the CMAQ emissions template file

        This may contain a date placeholder that will be replaced with the date of the emissions
    """
    with nc.Dataset(prior_file, mode="r") as input:
        prior_dates = nc.num2date(
            input["time"][:], input["time"].getncattr("units"), only_use_cftime_datetimes=False
        )
        emissions = input["ch4_total"][...]
        grid_shape = emissions.shape[2:]

    cmaq_spec = "CH4"
    for i, current_date in enumerate(prior_dates):
        met_cro_filename = replace_date(metcro_template, current_date)
        lens, attrDict = read_metcro(
            met_cro_filename, spec_list=[cmaq_spec], expected_grid_shape=grid_shape
        )

        ##  write this to file
        output_filename = replace_date(emis_template, current_date)

        # Create the parent directory if it doesn't exist
        Path(output_filename).parent.mkdir(parents=True, exist_ok=True)

        with nc.Dataset(
            output_filename, mode="w", format="NETCDF4_CLASSIC", clobber=True
        ) as output:
            # Write dimensions
            for k in lens.keys():
                output.createDimension(k, lens[k])

            # Create TFLAG variable
            outvars = {
                "TFLAG": output.createVariable(
                    "TFLAG",
                    "i4",
                    (
                        "TSTEP",
                        "VAR",
                        "DATE-TIME",
                    ),
                )
            }
            outvars["TFLAG"].setncattr("long_name", "{:<16}".format("TFLAG"))
            tflag_data = build_tflag_data(current_date, outvars["TFLAG"].shape)
            outvars["TFLAG"][...] = tflag_data

            # Create data variable
            outvars[cmaq_spec] = output.createVariable(
                cmaq_spec,
                "f4",
                ("TSTEP", "LAY", "ROW", "COL"),
                zlib=True,
                shuffle=False,
                ## one chunk per layer per time
                chunksizes=np.array([1, 1, *grid_shape]),
            )
            outvars[cmaq_spec].setncattr("long_name", f"{cmaq_spec:<16}")
            outvars[cmaq_spec].setncattr("units", "{:<16}".format("mols/s"))
            outvars[cmaq_spec].setncattr("var_desc", "{:<80}".format("Emissions of " + cmaq_spec))
            unit_conversion_factor = (
                attrDict["XCELL"] * attrDict["YCELL"] * KG_TO_G / MOLAR_MASS_CH4
            )  # from kg/m^2/s to moles/gridcell/s
            outvars[cmaq_spec][...] = 0.0
            outvars[cmaq_spec][:, 0, ...] = np.stack(
                [unit_conversion_factor * emissions[i, ...]] * lens["TSTEP"], axis=0
            )

            output.setncattr("HISTORY", "")
            # copy other attributes across
            for k, v in attrDict.items():
                output.setncattr(k, v)


if __name__ == "__main__":
    make_emissions_templates(
        prior_file=template_defn.prior_file,
        metcro_template=cmaq_config.met_cro_3d,
        emis_template=template_defn.emis,
    )
