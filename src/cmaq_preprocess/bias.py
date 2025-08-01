"""Functions for calculating and correcting bias between satellite measurements
and simulations."""

import datetime
import pathlib
import shutil

import numpy as np
import xarray as xr

from fourdvar.datadef import ObservationData

from . import utils
from .read_config_cmaq import CMAQConfig
import fourdvar.datadef as d
from fourdvar._transform import transform
from fourdvar.params.input_defn import obs_file, prior_file
from fourdvar.params.root_path_defn import store_path
from util.logger import get_logger

logger = get_logger(__name__)


def mass_weighted_mean(
    file_name: pathlib.Path,
    species: str,
    thickness: np.ndarray[float],
    region_inds: tuple = None,
) -> float:
    """
    returns three-dimensional thickness-weighted mean of species from netcdf file filename
    in ppm
    """
    logger.debug(f"file name: {file_name}")
    with xr.open_dataset(file_name) as ds:
        field = ds[species].to_numpy()
        vertical_integral = np.tensordot(field, thickness, (-3, 0)).squeeze()
        if region_inds is not None:
            region_slice = np.s_[
                region_inds[0][0] : region_inds[1][0] + 1, region_inds[0][1] : region_inds[1][1] + 1
            ]
        else:
            region_slice = np.s_[:, :]  # whole array
        logger.info(f"region slice, {region_slice} with mean: {vertical_integral[region_slice].mean()}")
        return vertical_integral[region_slice].mean()


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


def get_met_file(config: CMAQConfig) -> pathlib.Path:
    met_dir = utils.nested_dir(config.domain, config.start_date, config.met_dir)
    return met_dir / f"METCRO3D_{config.domain.mcip_suffix}"


def get_region(obs: ObservationData,
               date: datetime.date,
               ) -> tuple:
    date_string = date.strftime("%Y%m%d")
    lite_coords = [obs.lite_coord[d] for d in obs.ind_by_date[date_string]]
    llc_inds = (np.min([l[3] for l in lite_coords]), np.min([l[4] for l in lite_coords]))
    urc_inds = (np.max([l[3] for l in lite_coords]), np.max([l[4] for l in lite_coords]))
    return llc_inds, urc_inds



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
    levels: np.ndarray[float],
    correct_bias_by_region: bool = False,
        species: str='CH4',
) -> float:
    """Calculates the bias between iCon mean and satellite mean across the month.

    The bias is returned in units of ppm, with positive numbers meaning the satellite
    mean is higher.
    If correct_bias_by_region is True the correction is based on the spatial
    extent of TROPOMI observations on each day, otherwise it uses the entire domain
    """
    thickness = levels[:-1] - levels[1:]
    obs = ObservationData.from_file(obs_file)
    icon_means = []
    obs_means = []
    for i_date, date in enumerate(utils.date_range( start_date, end_date)):
        date_string = date.strftime("%Y%m%d")
        if len(obs.ind_by_date[date_string]) > 0:
            obs_means.append(np.mean(np.array(
                obs.value)[obs.ind_by_date[date_string]]))
            if correct_bias_by_region:
                region_inds = get_region(obs=obs, date=date)
            else:
                region_inds = None
            icon_mass_weighted_mean = mass_weighted_mean(icon_files[i_date],
                                                         species, thickness,
                                                         region_inds)
            icon_means.append( icon_mass_weighted_mean)
    icon_means = np.array(icon_means)
    obs_means = np.array(obs_means)
    logger.info(f"icon_means: {icon_means}")
    logger.info(f"obs_means: {obs_means}")
    obs_means /= 1000. # from ppb to ppm
    return obs_means.mean() - icon_means.mean()


def calculate_emissions_bias( prior_file: pathlib.Path,
                              obs_file: pathlib.Path,
                              species: str,
                             ) -> float:
    """ calculates the difference in simulated concentrations between a run with and without emissions.
    inputs: prior_file, path to prior emissions file,
    obs_file, path to observation file,
    species: name of species to solve for,
    returns: mean difference between simulated concentrations as a float.
    """
    prior = d.PhysicalData.from_file(prior_file)
    mean_obs_emis = calculate_mean_obs( prior, obs_file)
    prior.emis[species] *= 0. # zeroing emissions while preserving shape
    mean_obs_no_emis = calculate_mean_obs( prior, obs_file)
    return mean_obs_emis -mean_obs_no_emis

def calculate_mean_obs( physical: d.PhysicalData,
                        obs_file: pathlib.Path,
                        ) -> float:
    """ calculates mean concentrations arising from a PhysicalData object and
    an observation file.
    Inputs:
    physical: PhysicalData object carrying icon, bcon and emis fields
    obs_file: path to observation file
    returns: float, mean of simulated observations
    """
    modelInput = transform(physical, d.ModelInputData)
    modelOutput = transform(modelInput, d.ModelOutputData)
    observed = d.ObservationData.from_file(obs_file)
    simul = transform( modelOutput, d.ObservationData)
    return simul.get_vector().mean()/1000.

    
                        
    
