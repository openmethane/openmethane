from openmethane.cmaq_preprocess.bias import (
    calculate_forward_bias,
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
    bias = calculate_forward_bias(
        prior_file=input_defn.prior_file,
        obs_file=input_defn.obs_file,
    )
    logger.debug(f"bias={bias:f}")

    correct_icon_bcon(
        species=species,
        bias=bias,
        icon_files=[icon_files[0]],
        bcon_files=bcon_files,
    )


if __name__ == "__main__":
    main()
