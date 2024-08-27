import datetime
import os
import pathlib

import numpy as np
import xarray as xr

from cmaq_preprocess import utils
from cmaq_preprocess.read_config_cmaq import CMAQConfig, load_config_from_env
from fourdvar.datadef.observation_data import ObservationData
from fourdvar.params.input_defn import obs_file


def main():
    config = load_config_from_env()
    chem_dir = utils.nested_dir(config.domain, config.start_date, config.ctm_dir)
    icon_file = (
        chem_dir
        / f"{chem_dir}/ICON.{config.domain.id}.{config.domain.mcip_suffix}.{config.mech}.nc"
    )
    met_dir = utils.nested_dir(config.domain, config.start_date, config.met_dir)
    met_file = met_dir / f"METCRO3D_{config.domain.mcip_suffix}"
    levels = xr.open_dataset(met_file).VGLVLS
    bias = calculate_bias(config, icon_file, levels)
    print("bias ", bias)
    correct_icon_bcon(config, "CH4", bias)


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
    config: CMAQConfig,
    obs_file: pathlib.Path,
) -> float:
    obs = ObservationData.from_file(obs_file)
    # now find the earliest date with obs and return their mean
    one_day = datetime.timedelta(days=1)
    date = config.start_date
    while date <= config.end_date:
        date_string = date.strftime("%Y%m%d")
        if len(obs.ind_by_date[date_string]) > 0:
            return np.mean(np.array(obs.value)[obs.ind_by_date[date_string]])
        else:
            date += one_day
    raise ValueError("no valid observations found")


def correct_icon_bcon(config: CMAQConfig, species: str, bias: float):
    chem_dir = utils.nested_dir(config.domain, config.start_date, config.ctm_dir)
    icon_file = (
        chem_dir
        / f"{chem_dir}/ICON.{config.domain.id}.{config.domain.mcip_suffix}.{config.mech}.nc"
    )
    temp_file_name = "temp.nc"
    bcon_files = []
    one_day = datetime.timedelta(days=1)
    date = config.start_date
    while date <= config.end_date:
        bcon_dir = utils.nested_dir(config.domain, date, config.ctm_dir)
        bcon_file = (
            bcon_dir
            / f"{bcon_dir}/BCON.{config.domain.id}.{config.domain.mcip_suffix}.{config.mech}.nc"
        )
        bcon_files.append(bcon_file)
        date += one_day
    all_files = [*bcon_files, icon_file]
    for file in all_files:
        with xr.open_dataset(file) as ds:
            dss = ds.load()
            dss[species] += bias
            dss.to_netcdf(temp_file_name)
            os.rename(temp_file_name, file)


def calculate_bias(config: CMAQConfig, icon_file: pathlib.Path, levels: np.ndarray[float]) -> float:
    """Calculates the bias between ICON mean and satellite mean on the first day.

    The bias is returned in units of ppm, with positive numbers meaning the satellite
    mean is higher."""
    thickness = levels[:-1] - levels[1:]
    icon_mass_weighted_mean = mass_weighted_mean(icon_file, "CH4", thickness)
    satellite_mean_first_day = earliest_mean(config, obs_file)
    satellite_mean_first_day /= 1000.0  # ppb to ppm
    return satellite_mean_first_day - icon_mass_weighted_mean


if __name__ == "__main__":
    main()
