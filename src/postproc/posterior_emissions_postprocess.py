import logging
import numpy as np
import os
import pathlib
import xarray as xr

from postproc.calculate_average_emissions import calculate_average_emissions_moles

logger = logging.getLogger(__name__)

SPECIES_MOLEMASS = {"CH4": 16}  # molar mass in gram
G2KG = 1e-3  # conv factor kg to g


def posterior_emissions_postprocess(
    posterior_multipliers: np.ndarray,
    prior_emissions_ds: xr.Dataset,
    template_dir: pathlib.Path,
    emis_template: str = "emis_*.nc",
    species: str = "CH4",
) -> xr.Dataset:
    # copy dimensions and attributes from the prior emissions, as the posterior
    # emissions should be provided in the same grid / format
    logger.debug("creating Dataset from prior emissions data")
    posterior_emissions = xr.Dataset(
        data_vars={
            "latitude": (("y", "x"), prior_emissions_ds.variables["LAT"][0]),
            "longitude": (("y", "x"), prior_emissions_ds.variables["LON"][0]),
        },
        coords={
            "date": prior_emissions_ds.coords["date"],
            "x": prior_emissions_ds.coords["x"],
            "y": prior_emissions_ds.coords["y"],
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
        # prior_emissions_ds.copy(deep=True))

    # what most of our downstream consumers are interested in is the actual
    # "measurable" emissions, which we can produce by multiplying the fourdvar
    # result by the template emission (prior) in each cell.
    emissions_moles = calculate_average_emissions_moles(
        posterior_multipliers=normalise_posterior(posterior_multipliers),
        template_dir=template_dir,
        emis_template=emis_template,
    )

    logger.debug("converting emissions to kg/m**2/s")
    cell_area = posterior_emissions.DX * posterior_emissions.DY
    conv_fac = SPECIES_MOLEMASS[species] * G2KG
    posterior_emis_mean_output = emissions_moles * conv_fac / cell_area

    logger.debug("adding emissions to Dataset")
    posterior_emissions[species] = (('y', 'x'), posterior_emis_mean_output)
    posterior_emissions[species].attrs["units"] = "kg/m**2/s"
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
