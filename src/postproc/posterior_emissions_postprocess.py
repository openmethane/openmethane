#
# Copyright 2024 The Superpower Institute
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

import pathlib
import numpy as np
import xarray as xr

from postproc.calculate_average_emissions import calculate_average_emissions
from util.cf import get_grid_mappings
from util.logger import get_logger
from util.system import get_version, get_timestamped_command

logger = get_logger(__name__)


def posterior_emissions_postprocess(
    posterior_multipliers: np.ndarray,
    prior_emissions_ds: xr.Dataset,
    template_dir: pathlib.Path,
    emis_template: str = "emis_*.nc",
    species: str = "CH4",
) -> xr.Dataset:
    # what most of our downstream consumers are interested in is the actual
    # "measurable" emissions, which we can produce by multiplying the fourdvar
    # result by the template emission (prior) in each cell.
    emissions_array, prior_emissions_array, period_start, period_end = calculate_average_emissions(
        posterior_multipliers=normalise_posterior(posterior_multipliers),
        template_dir=template_dir,
        emis_template=emis_template,
        species=species,
    )

    # expand dimensions to include single-value "time", "vertical" coordinates
    emissions_np = np.expand_dims(emissions_array, axis=(0, 1))
    prior_emissions_np = np.expand_dims(prior_emissions_array, axis=(0, 1))

    # the domain typically has only one grid mapping, which applies to vars
    # with y, x coords
    projection_var_name = get_grid_mappings(prior_emissions_ds)[0]

    # copy dimensions and attributes from the prior emissions, as the posterior
    # emissions should be provided in the same grid / format
    logger.debug("creating Dataset from posterior emissions data with prior emissions structure")
    posterior_emissions_ds = xr.Dataset(
        coords={
            "x": prior_emissions_ds.coords["x"],
            "y": prior_emissions_ds.coords["y"],
            "time": (("time"), [period_start], {
                "standard_name": "time",
                "bounds": "time_bounds",
            }),
            # this dimension currently has no coordinate values, so it is left
            # as a dimension without coordinates
            # "vertical": (("vertical"), [0], {}),
        },
        data_vars={
            # bounds
            "x_bounds": prior_emissions_ds["x_bounds"],
            "y_bounds": prior_emissions_ds["y_bounds"],
            "time_bounds": (("time", "time_period"), [[period_start, period_end]]),

            # georeferencing
            "lon": prior_emissions_ds["lon"],
            "lat": prior_emissions_ds["lat"],
            projection_var_name: prior_emissions_ds[projection_var_name],

            # copied data
            "land_mask": prior_emissions_ds["land_mask"],
            "cell_name": prior_emissions_ds["cell_name"],

            # results data
            # posterior CH4 emissions - Open Methane primary result
            "ch4": (("time", "vertical", "y", "x"), emissions_np, {
                "units": "kg/m2/s",
                "standard_name": "surface_upward_mass_flux_of_methane",
                "long_name": "estimated flux of methane based on observations (posterior)",
                "grid_mapping": projection_var_name,
            }),
            # expected emissions (prior averaged over period)
            "prior_ch4": (("time", "vertical", "y", "x"), prior_emissions_np, {
                "units": "kg/m2/s",
                "standard_name": "surface_upward_mass_flux_of_methane",
                "long_name": "expected flux of methane based on public data (prior)",
                "grid_mapping": projection_var_name,
            }),
        },
        attrs={
            "DX": prior_emissions_ds.DX,
            "DY": prior_emissions_ds.DY,
            "XCELL": prior_emissions_ds.XCELL,
            "YCELL": prior_emissions_ds.YCELL,

            # domain
            "domain_name": prior_emissions_ds.domain_name,
            "domain_version": prior_emissions_ds.domain_version,
            "domain_slug": prior_emissions_ds.domain_slug,

            # meta
            "title": "Open Methane monthly emissions estimates",
            "comment": "Gridded emissions estimate for methane across Australia",
            "history": get_timestamped_command(),
            "openmethane_version": get_version(),
            "openmethane_prior_version": prior_emissions_ds.openmethane_prior_version,

            "Conventions": "CF-1.12",
        },
    )

    # ensure time and time_bounds use the same time encoding
    time_encoding = f"days since {period_start.strftime('%Y-%m-%d')}"
    posterior_emissions_ds.time.encoding["units"] = time_encoding
    posterior_emissions_ds.time_bounds.encoding["units"] = time_encoding

    # disable _FillValue for variables that shouldn't have empty values
    for var_name in ['time_bounds', 'x', 'y', 'x_bounds', 'y_bounds', 'lat', 'lon']:
        posterior_emissions_ds[var_name].encoding["_FillValue"] = None

    return posterior_emissions_ds


def normalise_posterior(
    posterior_multipliers: np.ndarray,
) -> np.ndarray:
    logger.debug("normalising posterior multipliers down to 2 dimensions")
    # we can't assume how many dimensions this will have, preserve the last two and average over all the rest
    PRESERVED_DIMENSIONS = 2
    if posterior_multipliers.ndim <= PRESERVED_DIMENSIONS:
        return posterior_multipliers

    averaged_dimensions = posterior_multipliers.ndim - PRESERVED_DIMENSIONS
    averaged_axes = tuple(range(averaged_dimensions))
    return posterior_multipliers.mean(axis=averaged_axes)
