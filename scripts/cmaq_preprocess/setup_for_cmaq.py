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

from cmaq_preprocess import utils
from cmaq_preprocess.cams import interpolate_from_cams_to_cmaq_grid
from cmaq_preprocess.cmaq_config import CMAQConfig, load_cmaq_config
from cmaq_preprocess.mcip import run_mcip
from cmaq_preprocess.mcip_preparation import check_input_met_and_output_folders, get_mcip_grid_names
from cmaq_preprocess.run_scripts import prepare_template_bcon_files, prepare_template_icon_files


@click.command()
@click.option(
    "-c",
    "--config-file",
    type=click.Path(exists=True),
    default="config/cmaq_preprocess/config.docker.json",
)
def main(config_file: str):
    config = load_cmaq_config(config_file)

    setup_for_cmaq(config)


def setup_for_cmaq(config: CMAQConfig):
    """
    Set up the CMAQ run

    This function runs MCIP, ICON and BCON to generate the required input files for running
    openmethane.

    Parameters
    ----------
    config
        Configuration to use
    """
    # define date range
    ndates = (config.end_date - config.start_date).days + 1
    dates = [config.start_date + datetime.timedelta(days=d) for d in range(ndates)]

    # read in the template run-scripts
    scripts = utils.load_scripts(scripts=config.scripts)

    # create output destinations, if need be:
    print("Check input meteorology files are provided and create output directories (if need be)")
    mcip_output_found = check_input_met_and_output_folders(
        config.ctm_dir, config.met_dir, dates, config.domains
    )
    print("\t... done")

    if (not mcip_output_found) or config.force_update:
        run_mcip(
            dates=dates,
            domains=config.domains,
            met_dir=config.met_dir,
            wrf_dir=config.wrf_dir,
            geo_dir=config.geo_dir,
            mcip_executable_dir=config.mcip_dir,
            scenario_tag=config.scenario_tag,
            map_projection_name=config.map_projection_name,
            grid_name=config.grid_name,
            scripts=scripts,
            compress_with_nco=True,
            fix_simulation_start_date=True,
        )

    # extract some parameters about the MCIP setup
    coord_names, grid_names, appl = get_mcip_grid_names(config.met_dir, dates, config.domains)

    if config.prepare_ic_and_bc:
        # prepare the template boundary condition concentration files
        # from profiles using BCON
        template_bcon_files = prepare_template_bcon_files(
            date=dates[0],
            domains=config.domains,
            ctm_dir=config.ctm_dir,
            met_dir=config.met_dir,
            cmaq_dir=config.cmaq_dir,
            simulation_name=config.run,
            mech=config.mech_cmaq,
            grid_names=grid_names,
            mcip_suffix=appl,
            scripts=scripts,
            force_update=config.force_update,
        )
        # prepare the template initial condition concentration files
        # from profiles using ICON
        template_icon_files = prepare_template_icon_files(
            date=dates[0],
            domains=config.domains,
            ctm_dir=config.ctm_dir,
            met_dir=config.met_dir,
            cmaq_dir=config.cmaq_dir,
            simulation_name=config.run,
            mech=config.mech_cmaq,
            grid_names=grid_names,
            mcip_suffix=appl,
            scripts=scripts,
            force_update=config.force_update,
        )
        # use the template initial and boundary condition concentration
        # files and populate them with values from CAMS output
        interpolate_from_cams_to_cmaq_grid(
            dates,
            config.domains,
            config.mech,
            config.input_cams_file,
            template_icon_files=template_icon_files,
            template_bcon_files=template_bcon_files,
            met_dir=config.met_dir,
            ctm_dir=config.ctm_dir,
            grid_names=grid_names,
            mcip_suffix=appl,
            force_update=config.force_update,
            bias_correct=config.cams_to_cmaq_bias,
        )


if __name__ == "__main__":
    main()
