import xarray as xr

from cmaq_preprocess import utils
from cmaq_preprocess.bias import calculate_bias, correct_icon_bcon
from cmaq_preprocess.read_config_cmaq import load_config_from_env


def main():
    """Correct the bias between the ICON mean and the satellite observation mean."""
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
    print(f"{bias=}")
    correct_icon_bcon(config, "CH4", bias)


if __name__ == "__main__":
    main()
