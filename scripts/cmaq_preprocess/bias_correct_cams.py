import datetime
import pathlib

import numpy as np
import xarray as xr

from fourdvar.datadef.observation_data import ObservationData
from fourdvar.params.input_defn import obs_file
from cmaq_preprocess import utils
from cmaq_preprocess.cams import interpolate_from_cams_to_cmaq_grid
from cmaq_preprocess.mcip import run_mcip
from cmaq_preprocess.mcip_preparation import (
    check_input_met_and_output_folders,
)
from cmaq_preprocess.read_config_cmaq import CMAQConfig, load_config_from_env
from cmaq_preprocess.run_scripts import (
    prepare_template_bcon_files,
    prepare_template_icon_files,
    )

def mass_weighted_mean( file_name: pathlib.Path, species: str, thickness: float) -> float:
    with xr.open_dataset( file_name) as ds:
        field = ds[species].to_numpy()
        vertical_integral = np.tensordot( field, thickness, (-3, 0))
        return vertical_integral.mean()

def earliest_mean( obs_file: pathlib.Path) -> float:
    obs = ObservationDate.from_file( obs_file)
    

def correct_icon_bcon( bias:  float):
    print('correct_icon_bcon ',bias)


config = load_config_from_env()
chem_dir = utils.nested_dir(config.domain, config.start_date, config.ctm_dir)
met_dir = utils.nested_dir(config.domain, config.start_date, config.met_dir)
icon_file = chem_dir / f"{chem_dir}/ICON.{config.domain.id}.{config.domain.mcip_suffix}.{config.mech}.nc"

met_file = met_dir / f"METCRO3D_{config.domain.mcip_suffix}"
levels = xr.open_dataset( met_file).VGLVLS
thickness = levels[0:-1] -levels[1:]

icon_mass_weighted_mean = mass_weighted_mean( icon_file, 'CH4', thickness)

satellite_mean_first_day = earliest_mean( obs_file)
bias = satellite_mean_first_day - icon_mass_weighted_mean
correct_icon_bcon( bias)
