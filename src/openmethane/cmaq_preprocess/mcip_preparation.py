"""Functions to check folders, files and attributes from MCIP output"""

import datetime
import os
import pathlib
import warnings

from openmethane.cmaq_preprocess.read_config_cmaq import Domain
from openmethane.cmaq_preprocess.utils import nested_dir


def check_input_met_and_output_folders(
    ctm_dir: pathlib.Path, met_dir: pathlib.Path, dates: list[datetime.date], domain: Domain
) -> bool:
    """
    Check that MCIP inputs are present, and create directories for CCTM input/output if need be

    Args:
        ctm_dir: base directory for the CCTM inputs and outputs
        met_dir: base directory for the MCIP output
        dates: list of datetime objects, one per date MCIP and CCTM output should be defined
        domain: Domain of interest

    Returns:
        True if all the required MCIP files are present, False if not
    """
    for idate, date in enumerate(dates):
        mcipdir = nested_dir(domain, date, met_dir)
        chemdir = nested_dir(domain, date, ctm_dir)

        if not os.path.exists(mcipdir):
            warnings.warn(f"MCIP output directory not found at {mcipdir}")
            return False

        ## create output destination
        chemdir.mkdir(parents=True, exist_ok=True)

        ## check that the MCIP GRIDDESC file is present
        griddesc_path = mcipdir / "GRIDDESC"

        if not os.path.exists(griddesc_path):
            warnings.warn(f"GRIDDESC file not found at {griddesc_path} ... ")
            return False

        ## check that the other MCIP output files are present
        mcip_files = [
            "GRIDBDY2D",
            "GRIDCRO2D",
            "GRIDDOT2D",
            "METBDY3D",
            "METCRO2D",
            "METCRO3D",
            "METDOT3D",
        ]
        for filetype in mcip_files:
            expected_filename = f"{filetype}_{domain.mcip_suffix}"

            if not (mcipdir / expected_filename).exists():
                warnings.warn(f"{expected_filename} file not found in folder {mcipdir}")
                return False
    return True
