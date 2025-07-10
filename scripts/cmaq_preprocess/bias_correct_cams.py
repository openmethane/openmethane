import os

import xarray as xr

import fourdvar.params.input_defn
from cmaq_preprocess.bias import (
    calculate_icon_bias,
    calculate_emissions_bias,
    correct_icon_bcon,
    get_bcon_files,
    get_icon_files,
    get_met_file,
)
from cmaq_preprocess.read_config_cmaq import load_config_from_env


def main():
    """Correct the bias between the iCon mean and the satellite observation mean."""
    config = load_config_from_env()
    icon_files = get_icon_files(config)
    bcon_files = get_bcon_files(config)
    met_file = get_met_file(config)
    correct_bias_by_region = os.getenv("DISABLE_CORRECT_BIAS_BY_REGION") != "true"
    levels = xr.open_dataset(met_file).attrs["VGLVLS"]
    icon_bias = calculate_icon_bias(
        icon_files=icon_files, 
        obs_file=fourdvar.params.input_defn.obs_file,
        levels=levels,
        start_date=config.start_date,
        end_date=config.end_date,
        correct_bias_by_region=correct_bias_by_region,
    )
    print(f"icon_bias={icon_bias:f}")
    emissions_bias = calculate_emissions_bias(
        start_date=config.start_date,
        end_date=config.end_date,
    )
    print(f"emissions_bias={emissions_bias:f}")
    total_bias = icon_bias + emissions_bias


    correct_icon_bcon(
        species="CH4",
        bias=total_bias,
        icon_files=[icon_files[0]],
        bcon_files=bcon_files,
    )


if __name__ == "__main__":
    main()
