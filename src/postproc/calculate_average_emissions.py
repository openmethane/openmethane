import glob
import logging
import pathlib

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)


def calculate_average_emissions_moles(
    posterior_multipliers: np.ndarray,
    template_dir: pathlib.Path,
    emis_template: str = "emis_*.nc",
    species: str = "CH4",
):
    prior_emis_files = list_emis_template_files(template_dir, emis_template)
    if len(prior_emis_files) == 0:
        raise ValueError(f"no emission template files found at {template_dir}")
    prior_emis_list = []
    logger.debug("loading prior emission templates")
    for filename in prior_emis_files:
        logger.debug(f"loading {filename}")
        with xr.open_dataset(filename) as xrds:
            # average over hours to get a single day average
            prior_emis_list.append(xrds[species].to_numpy().mean(axis=0))

    logger.debug("calculating 2 dimensional mean of template emissions")
    prior_emis_array = np.array(prior_emis_list)
    # average over days to get an average over the full period
    prior_emis_mean_3d = prior_emis_array.mean(axis=0)
    prior_emis_mean_surf = prior_emis_mean_3d[0, ...]

    logger.debug("multiplying averaged template emissions by posterior multipliers")
    return posterior_multipliers * prior_emis_mean_surf


def list_emis_template_files(
    template_dir: pathlib.Path,
    emis_template: str,
) -> list:
    prior_emis_glob = pathlib.Path(template_dir, "record", emis_template)
    prior_emis_files = glob.glob(str(prior_emis_glob))
    prior_emis_files.sort()
    return prior_emis_files
