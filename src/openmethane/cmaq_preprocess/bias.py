"""Functions for calculating and correcting bias between satellite measurements
and simulations."""

import datetime
import pathlib
import shutil

import numpy as np
import xarray as xr

import openmethane.fourdvar.datadef as d
from openmethane.fourdvar._transform import transform
from openmethane.util.logger import get_logger

from . import utils
from .read_config_cmaq import CMAQConfig

logger = get_logger(__name__)

# CMAQ carries mixing ratios in ppm, the retrieval reports columns in ppb
ppm2ppb = 1e3


def get_icon_files(config: CMAQConfig) -> list[pathlib.Path]:
    icon_files = []
    for date in utils.date_range(config.start_date, config.end_date):
        chem_dir = utils.nested_dir(config.domain, date, config.ctm_dir)
        icon_files.append(
            chem_dir / f"ICON.{config.domain.id}.{config.domain.mcip_suffix}.{config.mech}.nc"
        )
    return icon_files


def get_bcon_files(config: CMAQConfig) -> list[pathlib.Path]:
    bcon_files = []
    for date in utils.date_range(config.start_date, config.end_date):
        chem_dir = utils.nested_dir(config.domain, date, config.ctm_dir)
        bcon_files.append(
            chem_dir / f"BCON.{config.domain.id}.{config.domain.mcip_suffix}.{config.mech}.nc"
        )
    return bcon_files


def mean_weight_sum(obs: d.ObservationData, indices: list[int] | None = None) -> float:
    """Mean over observations of the total weight their operator puts on the model.

    The column operator is affine, `y = ppm2ppb * sum_c w_c x_c + b`, so a
    uniform shift of `dx` ppm in the concentration field moves a simulated
    column by `ppm2ppb * sum_c w_c * dx` ppb rather than by `ppm2ppb * dx`. The
    operational TROPOMI kernel is normalised so that this total is one, but
    nothing in the operator guarantees it, so corrections expressed as a
    concentration are divided by it.
    """
    if indices is None:
        indices = range(obs.length)
    return float(np.mean([sum(obs.weight_grid[i].values()) for i in indices]))


def simulate_static_columns(
    file_name: pathlib.Path,
    obs: d.ObservationData,
    indices: list[int],
) -> np.ndarray:
    """Simulate a set of observations from a single, time-invariant concentration field.

    Applies each observation's own column operator to the field, exactly as
    `fourdvar.transfunc.obs_operator` applies it to the forward model's
    concentrations:

        y_i = ppm2ppb * sum_c w_ic x_c + b_i

    with `w_i` the observation's `weight_grid`, `b_i` its `offset_term` and `x`
    the field in ppm. Doing the comparison this way rather than against a
    mass-weighted column mean keeps the averaging kernel, the retrieval's
    `(1 - A) x_a` term and the treatment of the column above the model top on
    the same footing as in the inversion. It also confines the comparison to
    the cells the observations actually see, so no separate regional masking is
    needed.

    Parameters
    ----------
    file_name
        Path to a netCDF file holding a single record of the concentration
        field, i.e. an ICON file.
    obs
        Observations, loaded from a full (not lite) observation file.
    indices
        Indices of the observations to simulate.

    Returns
    -------
        The simulated columns in ppb, one per entry in `indices`.
    """
    simulated = []
    with xr.open_dataset(file_name) as ds:
        fields = {}
        for i in indices:
            total = 0.0
            for coord, weight in obs.weight_grid[i].items():
                _, _, lay, row, col, spc = coord
                if spc not in fields:
                    field = ds[spc].to_numpy()
                    # the field is a single record standing for the whole run,
                    # so the observation's time step is ignored
                    fields[spc] = field[0] if field.ndim == 4 else field
                total += weight * fields[spc][lay, row, col]
            simulated.append(ppm2ppb * total + obs.offset_term[i])
    return np.array(simulated)


def correct_icon_bcon(
    species: str,
    bias: float,
    icon_files: list[pathlib.Path],
    bcon_files: list[pathlib.Path],
):
    all_files = [*bcon_files, *icon_files]
    temp_file_name = "temp.nc"
    for file in all_files:
        with xr.open_dataset(file) as ds:
            dss = ds.load()
            dss[species] += bias
            dss.to_netcdf(temp_file_name)
            shutil.move(temp_file_name, file)


def calculate_icon_bias(
    start_date: datetime.date,
    end_date: datetime.date,
    icon_files: list[pathlib.Path],
    obs_file: pathlib.Path,
) -> float:
    """Calculate the bias between the CAMS background and the satellite across the month.

    Both sides of the comparison are put in the space the inversion works in:
    the satellite columns as reported, and the columns the observation operator
    would simulate from the initial condition field alone (see
    `simulate_static_columns`). Each day contributes its mean equally.

    The bias is returned in ppm, as the shift to add to the concentration field,
    with positive numbers meaning the satellite sees more methane than the
    background provides. Because the operator puts a total weight of `W` on the
    model, a shift of `dx` ppm only moves a simulated column by
    `ppm2ppb * W * dx` ppb, so the residual is divided by the mean weight.
    """
    obs = d.ObservationData.from_file(obs_file)
    icon_means = []
    obs_means = []
    weight_sums = []
    for i_date, date in enumerate(utils.date_range(start_date, end_date)):
        date_string = date.strftime("%Y%m%d")
        indices = obs.ind_by_date[date_string]
        if len(indices) == 0:
            continue
        obs_means.append(np.mean(np.array(obs.value)[indices]))
        icon_means.append(simulate_static_columns(icon_files[i_date], obs, indices).mean())
        weight_sums.append(mean_weight_sum(obs, indices))
    icon_means = np.array(icon_means)
    obs_means = np.array(obs_means)
    logger.info(f"icon column means (ppb): {icon_means}")
    logger.info(f"obs column means (ppb): {obs_means}")
    weight_sum = np.mean(weight_sums)
    logger.info(f"mean operator weight: {weight_sum}")
    return (obs_means.mean() - icon_means.mean()) / (ppm2ppb * weight_sum)


def calculate_emissions_bias(
    prior_file: pathlib.Path,
    obs_file: pathlib.Path,
    species: str,
) -> float:
    """Calculate the concentration the prior emissions add to the simulated columns.

    Runs the forward model with and without the prior emissions and differences
    the mean simulated observations. The offset term is the same in both runs,
    so it cancels; what remains is divided by the mean operator weight to
    express it, like the ICON bias, as a shift in ppm of the concentration
    field.

    inputs: prior_file, path to prior emissions file,
    obs_file, path to observation file,
    species: name of species to solve for,
    returns: the emissions' contribution as a concentration in ppm.
    """
    prior = d.PhysicalData.from_file(prior_file)
    mean_obs_emis = calculate_mean_obs(prior, obs_file)
    prior.emis[species] *= 0.0  # zeroing emissions while preserving shape
    mean_obs_no_emis = calculate_mean_obs(prior, obs_file)
    # calculate_mean_obs has just loaded obs_file, so this reads the same data
    weight_sum = mean_weight_sum(d.ObservationData.from_file(obs_file))
    return (mean_obs_emis - mean_obs_no_emis) / (ppm2ppb * weight_sum)


def calculate_mean_obs(
    physical: d.PhysicalData,
    obs_file: pathlib.Path,
) -> float:
    """calculates mean concentrations arising from a PhysicalData object and
    an observation file.
    Inputs:
    physical: PhysicalData object carrying icon, bcon and emis fields
    obs_file: path to observation file
    returns: float, mean of simulated observations in ppb
    """
    modelInput = transform(physical, d.ModelInputData)
    modelOutput = transform(modelInput, d.ModelOutputData)
    # loading the observations sets the operator parameters the transform below
    # reads off the ObservationData class
    d.ObservationData.from_file(obs_file)
    simul = transform(modelOutput, d.ObservationData)
    return simul.get_vector().mean()
