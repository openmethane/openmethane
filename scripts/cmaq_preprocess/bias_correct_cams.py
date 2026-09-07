from openmethane.cmaq_preprocess.bias import (
    calculate_emissions_bias,
    calculate_icon_bias,
    correct_icon_bcon,
    get_bcon_files,
    get_icon_files,
)
from openmethane.cmaq_preprocess.read_config_cmaq import load_config_from_env
from openmethane.fourdvar.params import input_defn
from openmethane.util.logger import get_logger

logger = get_logger(__name__)


def main():
    """Correct the bias between the simulated CAMS background and the satellite columns."""
    config = load_config_from_env()
    species = "CH4"
    icon_files = get_icon_files(config)
    bcon_files = get_bcon_files(config)
    icon_bias = calculate_icon_bias(
        icon_files=icon_files,
        obs_file=input_defn.obs_file,
        start_date=config.start_date,
        end_date=config.end_date,
    )
    logger.debug(f"icon_bias={icon_bias:f}")
    emissions_bias = calculate_emissions_bias(
        prior_file=input_defn.prior_file,
        obs_file=input_defn.obs_file,
        species=species,
    )
    logger.debug(f"emissions_bias={emissions_bias:f}")
    total_bias = icon_bias - emissions_bias

    correct_icon_bcon(
        species=species,
        bias=total_bias,
        icon_files=[icon_files[0]],
        bcon_files=bcon_files,
    )


if __name__ == "__main__":
    main()
