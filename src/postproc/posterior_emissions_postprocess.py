import logging
import numpy as np
import os
import pathlib
import xarray as xr

from postproc.calculate_average_emissions import calculate_average_emissions

logger = logging.getLogger(__name__)


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
    emissions_array, period_start, period_end = calculate_average_emissions(
        posterior_multipliers=normalise_posterior(posterior_multipliers),
        template_dir=template_dir,
        emis_template=emis_template,
        species=species,
    )

    # create a variable with projection coordinates
    projection_x = prior_emissions_ds.XORIG + (0.5 * prior_emissions_ds.XCELL) + np.arange(len(prior_emissions_ds.COL)) * prior_emissions_ds.XCELL
    projection_y = prior_emissions_ds.YORIG + (0.5 * prior_emissions_ds.YCELL) + np.arange(len(prior_emissions_ds.ROW)) * prior_emissions_ds.YCELL

    # copy dimensions and attributes from the prior emissions, as the posterior
    # emissions should be provided in the same grid / format
    logger.debug("creating Dataset from posterior emissions data with prior emissions structure")
    posterior_emissions = xr.Dataset(
        data_vars={
            "latitude": (("y", "x"), prior_emissions_ds.variables["LAT"][0]),
            "longitude": (("y", "x"), prior_emissions_ds.variables["LON"][0]),
            "time_bounds": (("time", "nv"), [[period_start, period_end]]),
            # https://cfconventions.org/Data/cf-conventions/cf-conventions-1.11/cf-conventions.html#_lambert_conformal
            "grid_projection": ((), 0, {
                "grid_mapping_name": "lambert_conformal_conic",
                "standard_parallel": (prior_emissions_ds.TRUELAT1, prior_emissions_ds.TRUELAT2),
                "longitude_of_central_meridian": prior_emissions_ds.STAND_LON,
                "latitude_of_projection_origin": prior_emissions_ds.MOAD_CEN_LAT,
            }),
            "projection_x": (("x"), projection_x, {
                "long_name": "x coordinate of projection",
                "units": "m",
                "standard_name": "projection_x_coordinate",
            }),
            "projection_y": (("y"), projection_y, {
                "long_name": "y coordinate of projection",
                "units": "m",
                "standard_name": "projection_y_coordinate",
            }),
            "time_bounds": (("time", "bounds_t"), [[period_start, period_end]]),
            "CH4": (("time", "y", "x"), [emissions_array], { "units": "kg/m**2/s" }),
        },
        coords={
            "x": prior_emissions_ds.coords["x"],
            "y": prior_emissions_ds.coords["y"],
            "time": (("time"), [period_start], { "bounds": "time_bounds" }),
        },
        attrs={
            "DX": prior_emissions_ds.DX,
            "DY": prior_emissions_ds.DY,
            "XCELL": prior_emissions_ds.XCELL,
            "YCELL": prior_emissions_ds.YCELL,
            "title": "Open Methane monthly emissions estimates",
            "openmethane_version": os.getenv("OPENMETHANE_VERSION", "development"),
            "history": "",
        },
    )

    return posterior_emissions


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
