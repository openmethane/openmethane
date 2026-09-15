"""Offset the boundary conditions of a prepared run by a known amount.

Runs between `cmaq_preprocess` and `fourdvar`, in the same place as the CAMS
bias correction, and rewrites each day's BCON file in place. The forward run
that follows then measures the column response to a known boundary
perturbation.

Only the whole perimeter is supported. Per-edge and per-layer perturbations are
the later stages of the experiment and depend on resolving CMAQ's corner
convention first.
"""

import argparse

from openmethane.cmaq_preprocess.bcon_perturbation import perturb_bcon_files
from openmethane.cmaq_preprocess.bias import get_bcon_files
from openmethane.cmaq_preprocess.read_config_cmaq import load_config_from_env
from openmethane.util.logger import get_logger

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offset-ppb",
        type=float,
        required=True,
        help="offset added to the boundary concentrations, in ppb",
    )
    parser.add_argument("--species", default="CH4", help="species to perturb")
    args = parser.parse_args()

    config = load_config_from_env()
    bcon_files = get_bcon_files(config)
    logger.info(f"perturbing {len(bcon_files)} BCON files by {args.offset_ppb:+g} ppb")
    perturb_bcon_files(bcon_files, offset_ppb=args.offset_ppb, species=args.species)


if __name__ == "__main__":
    main()
