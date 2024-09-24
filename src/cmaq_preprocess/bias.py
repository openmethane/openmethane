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
    file_name: pathlib.Path, species: str, thickness: np.ndarray[float]
) -> float:
    """
    returns three-dimensional thickness-weighted mean of species from netcdf file filename
    in ppm
    """
    with xr.open_dataset(file_name) as ds:
        field = ds[species].to_numpy()
        vertical_integral = np.tensordot(field, thickness, (-3, 0))
        return vertical_integral.mean()


def earliest_mean(
    start_date: datetime.date,
    end_date: datetime.date,
    obs_file: pathlib.Path,
) -> float:
    obs = ObservationData.from_file(obs_file)
    # now find the earliest date with obs and return their mean
    one_day = datetime.timedelta(days=1)
    date = start_date
    while date <= end_date:
        date_string = date.strftime("%Y%m%d")
        if len(obs.ind_by_date[date_string]) > 0:
            return np.mean(np.array(obs.value)[obs.ind_by_date[date_string]])
        else:
            date += one_day
    raise ValueError("no valid observations found")


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
) -> float:
    """Calculates the bias between iCon mean and satellite mean on the first day.

    The bias is returned in units of ppm, with positive numbers meaning the satellite
    mean is higher."""
    thickness = levels[:-1] - levels[1:]
    icon_mass_weighted_mean = mass_weighted_mean(icon_file, "CH4", thickness)
    satellite_mean_first_day = earliest_mean(
        obs_file=obs_file, start_date=start_date, end_date=end_date
    )
    satellite_mean_first_day /= 1000.0  # ppb to ppm
    return satellite_mean_first_day - icon_mass_weighted_mean
