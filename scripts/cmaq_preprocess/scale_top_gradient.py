"""Rescale the methane gradient above a chosen layer in a prepared run.

Runs between `cmaq_preprocess` and `fourdvar`, in the same place as the CAMS
bias correction, and rewrites each day's ICON and BCON file in place. The
forward run that follows then shows whether the drift reported in #248 depends
on the gradient at the model top.

`--scale 1` is the identity and is what the baseline arm runs, so that both arms
go through the same code and differ only in the number. `--scale 0` removes the
gradient.

Every ICON file is rewritten, although the model reads only the first day's:
`bias_correct_cams.py` corrects `icon_files[0]` and every BCON, and later days
restart from the previous day's CGRID. The rest are rewritten so that the
diagnostic which compares the run against its own day's CAMS field compares it
against the field the arm was actually built on.
"""

import argparse

from openmethane.cmaq_preprocess.bias import get_bcon_files, get_icon_files
from openmethane.cmaq_preprocess.read_config_cmaq import load_config_from_env
from openmethane.cmaq_preprocess.top_gradient import scale_top_gradient
from openmethane.util.logger import get_logger

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scale",
        type=float,
        required=True,
        help="multiplier on the profile's departure from the anchor layer; "
        "1 is the identity, 0 removes the gradient",
    )
    parser.add_argument(
        "--anchor-layer",
        type=int,
        default=23,
        help="zero-based layer the rescaled profile is pinned to; layers at or "
        "below it are untouched (default: 23, about 220 hPa)",
    )
    parser.add_argument("--species", default="CH4", help="species to rewrite")
    args = parser.parse_args()

    config = load_config_from_env()
    files = [*get_icon_files(config), *get_bcon_files(config)]
    logger.info(
        f"rescaling {args.species} above layer {args.anchor_layer} by "
        f"{args.scale:g} in {len(files)} files"
    )
    scale_top_gradient(
        files,
        anchor_layer=args.anchor_layer,
        scale=args.scale,
        species=args.species,
    )


if __name__ == "__main__":
    main()
