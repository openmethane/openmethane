## Top level run script for the preparation phase
#
# This is the top-level script that sets up the CMAQ inputs. Most of
# the detail and functionality is found in a series of accompanying
# files. Tasks performed:
#  - create output destinations (if need be)
#  - check the latitudes and longitudes of the WRF and MCIP grids against one another
#  - prepare run scripts for ICON, BCON and CCTM programs within the CMAQ  bundle
#
# Author: Jeremy Silver (jeremy.silver@unimelb.edu.au)
# Date: 2016-11-04


import datetime

import click

from openmethane.cmaq_preprocess import utils
from openmethane.cmaq_preprocess.cams import interpolate_from_cams_to_cmaq_grid
from openmethane.cmaq_preprocess.mcip import run_mcip
from openmethane.cmaq_preprocess.mcip_preparation import (
    check_input_met_and_output_folders,
)
from openmethane.cmaq_preprocess.read_config_cmaq import CMAQConfig, load_config_from_env
from openmethane.cmaq_preprocess.run_scripts import (
    prepare_template_bcon_files,
    prepare_template_icon_files,
)


@click.command()
def main():
    config = load_config_from_env()

    setup_for_cmaq(config)


def setup_for_cmaq(config: CMAQConfig):
    # define date range
    ndates = (config.end_date - config.start_date).days + 1
    dates = [config.start_date + datetime.timedelta(days=d) for d in range(ndates)]

    # create output destinations, if need be:
    print("Check that input meteorology files are provided and create output destinations")
    mcip_output_found = check_input_met_and_output_folders(
        config.ctm_dir, config.met_dir, dates, config.domain
    )
    if mcip_output_found:
        print("Existing MCIP output found")

    print("\t... done")

    if (not mcip_output_found) or config.force_update:
        run_mcip(
            dates=dates,
            domain=config.domain,
            met_dir=config.met_dir,
            wrf_dir=config.wrf_dir,
            geo_dir=config.geo_dir,
            mcip_bin_dir=config.cmaq_bin_dir,
            mcip_run_path=config.cmaq_scripts_dir / "run.mcip",
            compress_output=True,
            fix_simulation_start_date=True,
            truelat2=None,
            boundary_trim=config.boundary_trim,
        )

    if config.prepare_ic_and_bc:
        # prepare the template boundary condition concentration files
        # from profiles using BCON
        template_bcon_files = prepare_template_bcon_files(
            date=dates[0],
            domain=config.domain,
            ctm_dir=config.ctm_dir,
            met_dir=config.met_dir,
            mech=config.mech,
            cmaq_bin_dir=config.cmaq_bin_dir,
            bcon_run_path=config.cmaq_scripts_dir / "run.bcon",
            forceUpdate=config.force_update,
        )
        # prepare the template initial condition concentration files
        # from profiles using ICON
        template_icon_files = prepare_template_icon_files(
            date=dates[0],
            domain=config.domain,
            ctm_dir=config.ctm_dir,
            met_dir=config.met_dir,
            mech=config.mech,
            cmaq_bin_dir=config.cmaq_bin_dir,
            icon_run_path=config.cmaq_scripts_dir / "run.icon",
            forceUpdate=config.force_update,
        )
        # use the template initial and boundary condition concentration
        # files and populate them with values from MOZART output
        interpolate_from_cams_to_cmaq_grid(
            dates=dates,
            domain=config.domain,
            mech=config.mech,
            input_cams_file=config.input_cams_file,
            template_icon_file=template_icon_files,
            template_bcon_file=template_bcon_files,
            met_dir=config.met_dir,
            ctm_dir=config.ctm_dir,
            force_update=config.force_update,
            bias_correct=config.cams_to_cmaq_bias,
        )


if __name__ == "__main__":
    main()
