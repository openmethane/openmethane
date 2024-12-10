import os
import xarray as xr

import fourdvar.params.input_defn
from cmaq_preprocess.bias import (
    calculate_bias,
    correct_icon_bcon,
    get_bcon_files,
    get_icon_file,
    get_met_file,
)
from cmaq_preprocess.read_config_cmaq import load_config_from_env


def main():
    """Correct the bias between the iCon mean and the satellite observation mean."""
    config = load_config_from_env()
    icon_file = get_icon_file(config)
    bcon_files = get_bcon_files(config)
    met_file = get_met_file(config)
    if os.getenv('CORRECT_BIAS_BY_REGION') is not None:
        correct_bias_by_region = True
    else:
        correct_bias_by_region = False
    levels = xr.open_dataset(met_file).attrs["VGLVLS"]
    bias = calculate_bias(
        icon_file=icon_file,
        obs_file=fourdvar.params.input_defn.obs_file,
        levels=levels,
        start_date=config.start_date,
        end_date=config.end_date,
        correct_bias_by_region=correct_bias_by_region,
    )

    print(f"{bias=}")

    correct_icon_bcon(
        species="CH4",
        bias=bias,
        icon_file=icon_file,
        bcon_files=bcon_files,
    )


if __name__ == "__main__":
    main()
