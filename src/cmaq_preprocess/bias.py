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


def mass_weighted_mean(
        file_name: pathlib.Path, species: str, thickness: np.ndarray[float],
        region_inds: tuple = None,
) -> float:
    """
    returns three-dimensional thickness-weighted mean of species from netcdf file filename
    in ppm
    """
    with xr.open_dataset(file_name) as ds:
        field = ds[species].to_numpy()
        vertical_integral = np.tensordot(field, thickness, (-3, 0)).squeeze()
        if region_inds is not None:
            region_slice = np.s_[region_inds[0][0]:region_inds[1][0]+1,
                                 region_inds[1][0]:region_inds[1][1]+1]
        else:
            region_slice = np.s_[:,:] # whole array
        print('region slice',region_slice,vertical_integral[region_slice].mean())
        return vertical_integral[ region_slice].mean()
def earliest_observation_date(
        start_date: datetime.date,
        end_date: datetime.date,
        obs: ObservationData,
        ) -> datetime.datetime:
    """
    takes an observation dataset and returns the first day with observations
    """
    one_day = datetime.timedelta(days=1)
    date = start_date
    while date <= end_date:
        date_string = date.strftime("%Y%m%d")
        if len(obs.ind_by_date[date_string]) > 0:
            return date
        else:
            date += one_day
    return None
                               

def earliest_mean(
    start_date: datetime.date,
    end_date: datetime.date,
    obs_file: pathlib.Path,
) -> float:
    obs = ObservationData.from_file(obs_file)
    earliest_date = earliest_observation_date( start_date, end_date, obs)
    if earliest_date is None:
        raise ValueError("no valid observations found")
    date_string = earliest_date.strftime("%Y%m%d")
    return np.mean(np.array(obs.value)[obs.ind_by_date[date_string]])


def earliest_region(
    start_date: datetime.date,
    end_date: datetime.date,
    obs_file: pathlib.Path,
) -> tuple:
    obs = ObservationData.from_file(obs_file)
    earliest_date = earliest_observation_date( start_date, end_date, obs)
    if earliest_date is None:
        raise ValueError("no valid observations found")
    date_string = earliest_date.strftime("%Y%m%d")
    lite_coords = [obs.lite_coord[d] for d in obs.ind_by_date[date_string]]
    llc_inds = (np.min([l[3] for l in lite_coords]),
                np.min([l[4] for l in lite_coords]))
    urc_inds = (np.max([l[3] for l in lite_coords]),
                np.max([l[4] for l in lite_coords]))
    return llc_inds, urc_inds

def get_icon_file(config: CMAQConfig) -> pathlib.Path:
    chem_dir = utils.nested_dir(config.domain, config.start_date, config.ctm_dir)
    return chem_dir / f"ICON.{config.domain.id}.{config.domain.mcip_suffix}.{config.mech}.nc"


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


def correct_icon_bcon(
    species: str,
    bias: float,
    icon_file: pathlib.Path,
    bcon_files: list[pathlib.Path],
):
    all_files = [*bcon_files, icon_file]
    temp_file_name = "temp.nc"
    for file in all_files:
        with xr.open_dataset(file) as ds:
            dss = ds.load()
            dss[species] += bias
            dss.to_netcdf(temp_file_name)
            shutil.move(temp_file_name, file)


def calculate_bias(
    start_date: datetime.date,
    end_date: datetime.date,
    icon_file: pathlib.Path,
    obs_file: pathlib.Path,
    levels: np.ndarray[float],
    correct_bias_by_region: bool = False,
) -> float:
    """Calculates the bias between iCon mean and satellite mean on the first day.

    The bias is returned in units of ppm, with positive numbers meaning the satellite
    mean is higher.
    If correct_bias_by_region is True the correction is based on the spatial
    extent of TROPOMI observations on the first day, otherwise it uses the entire domain
    """
    thickness = levels[:-1] - levels[1:]
    satellite_mean_first_day = earliest_mean(
        obs_file=obs_file, start_date=start_date, end_date=end_date
    )
    satellite_mean_first_day /= 1000.0  # ppb to ppm
    if correct_bias_by_region:
        region_inds = earliest_region(
            obs_file=obs_file, start_date=start_date, end_date=end_date
        )
    else:
        region_inds = None
    icon_mass_weighted_mean = mass_weighted_mean(icon_file, "CH4", thickness, region_inds)
    return satellite_mean_first_day - icon_mass_weighted_mean
