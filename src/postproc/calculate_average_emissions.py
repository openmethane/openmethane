from datetime import datetime, timedelta
import glob
import logging
import pathlib

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

SPECIES_MOLEMASS = {"CH4": 16}  # molar mass in gram
G2KG = 1e-3  # conv factor kg to g


def calculate_average_emissions(
    posterior_multipliers: np.ndarray,
    template_dir: pathlib.Path,
    emis_template: str = "emis_*.nc",
    species: str = "CH4",
):
    prior_emis_files = list_emis_template_files(template_dir, emis_template)
    if len(prior_emis_files) == 0:
        raise ValueError(f"no emission template files found at {template_dir}")

    prior_emis_cell_area = None
    prior_emis_start = None
    prior_emis_end = None
    prior_emis_list = []
    logger.debug("loading prior emission templates")
    for filename in prior_emis_files:
        logger.debug(f"loading {filename}")
        with xr.open_dataset(filename) as prior_emis_day_ds:
            day = datetime.strptime(str(prior_emis_day_ds.SDATE), "%Y%j") # format is <YEAR><DAY OF YEAR>
            if prior_emis_cell_area is None:
                prior_emis_cell_area = prior_emis_day_ds.XCELL * prior_emis_day_ds.YCELL
            if prior_emis_start is None or day < prior_emis_start:
                prior_emis_start = day
            if prior_emis_end is None or day > prior_emis_end:
                prior_emis_end = day

            # average over hours to get a single day average
            prior_emis_list.append(prior_emis_day_ds[species].to_numpy().mean(axis=0))

    logger.debug("calculating 2 dimensional mean of template emissions")
    prior_emis_array = np.array(prior_emis_list)
    # average over days to get an average over the full period
    prior_emis_mean_3d = prior_emis_array.mean(axis=0)
    prior_emis_mean_surf = prior_emis_mean_3d[0, ...]

    logger.debug("multiplying averaged template emissions by posterior multipliers")
    posterior_emissions_array = posterior_multipliers * prior_emis_mean_surf

    logger.debug("converting emissions to kg/m**2/s")
    conv_fac = SPECIES_MOLEMASS[species] * G2KG
    posterior_emis_mean_output = posterior_emissions_array * conv_fac / prior_emis_cell_area

    # each file covers a full day, so add 1d to the end date for the full period
    return (posterior_emis_mean_output, prior_emis_start, prior_emis_end + timedelta(days=1))


def list_emis_template_files(
    template_dir: pathlib.Path,
    emis_template: str,
) -> list:
    prior_emis_glob = pathlib.Path(template_dir, "record", emis_template)
    prior_emis_files = glob.glob(str(prior_emis_glob))
    prior_emis_files.sort()
    return prior_emis_files
