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
from cmaq_preprocess.mcip import runMCIP
from cmaq_preprocess.mcip_preparation import (
    check_input_met_and_output_folders,
    get_mcip_grid_names,
)
from cmaq_preprocess.read_config_cmaq import CMAQConfig, load_cmaq_config
from cmaq_preprocess.run_scripts import (
    prepare_bcon_run_scripts,
    prepare_main_run_script,
    prepare_template_bcon_files,
    prepare_template_icon_files,
)


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
    # define date range
    ndates = (config.endDate - config.startDate).days + 1
    dates = [config.startDate + datetime.timedelta(days=d) for d in range(ndates)]

    # read in the template run-scripts
    scripts = utils.load_scripts(scripts=config.scripts)

    # create output destinations, if need be:
    print(
        "Check that input meteorology files are provided and create output destinations (if need be)"
    )
    mcip_output_found = check_input_met_and_output_folders(
        config.ctmDir, config.metDir, dates, config.domains
    )
    print("\t... done")

    if (not mcip_output_found) or config.forceUpdateMcip:
        runMCIP(
            dates=dates,
            domains=config.domains,
            metDir=config.metDir,
            wrfDir=config.wrfDir,
            geoDir=config.geoDir,
            ProgDir=config.MCIPdir,
            APPL=config.scenarioTag,
            CoordName=config.mapProjName,
            GridName=config.gridName,
            scripts=scripts,
            compressWithNco=True,
            fix_simulation_start_date=True,
            fix_truelat2=False,
            truelat2=None,
            wrfRunName=None,
            doArchiveWrf=False,
            add_qsnow=config.add_qsnow,
        )

    # extract some parameters about the MCIP setup
    coord_names, grid_names, appl = get_mcip_grid_names(config.metDir, dates, config.domains)

    if config.prepareICandBC:
        # prepare the template boundary condition concentration files
        # from profiles using BCON
        template_bcon_files = prepare_template_bcon_files(
            date=dates[0],
            domains=config.domains,
            ctm_dir=config.ctmDir,
            met_dir=config.metDir,
            cmaq_dir=config.CMAQdir,
            simulation_name=config.run,
            mech=config.mechCMAQ,
            grid_names=grid_names,
            mcip_suffix=appl,
            scripts=scripts,
            force_update=config.forceUpdateICandBC,
        )
        # prepare the template initial condition concentration files
        # from profiles using ICON
        template_icon_files = prepare_template_icon_files(
            date=dates[0],
            domains=config.domains,
            ctm_dir=config.ctmDir,
            met_dir=config.metDir,
            cmaq_dir=config.CMAQdir,
            simulation_name=config.run,
            mech=config.mechCMAQ,
            grid_names=grid_names,
            mcip_suffix=appl,
            scripts=scripts,
            force_update=config.forceUpdateICandBC,
        )
        # use the template initial and boundary condition concentration
        # files and populate them with values from MOZART output
        interpolate_from_cams_to_cmaq_grid(
            dates,
            config.domains,
            config.mech,
            config.inputCAMSFile,
            template_icon_files=template_icon_files,
            template_bcon_files=template_bcon_files,
            met_dir=config.metDir,
            ctm_dir=config.ctmDir,
            grid_names=grid_names,
            mcip_suffix=appl,
            force_update=config.forceUpdateICandBC,
            bias_correct=config.CAMSToCmaqBiasCorrect,
        )

    if config.prepareRunScripts:
        print("Prepare ICON, BCON run scripts")
        # prepare the scripts for BCON
        prepare_bcon_run_scripts(
            sufadjname=config.sufadj,
            dates=dates,
            domains=config.domains,
            ctmDir=config.ctmDir,
            metDir=config.metDir,
            CMAQdir=config.CMAQdir,
            CFG=config.run,
            mech=config.mech,
            mechCMAQ=config.mechCMAQ,
            GridNames=grid_names,
            mcip_suffix=appl,
            scripts=scripts,
            force_update=config.forceUpdateRunScripts,
        )
        # prepare the main run script
        prepare_main_run_script(
            dates=dates,
            domains=config.domains,
            ctm_dir=config.ctmDir,
            cmaq_dir=config.CMAQdir,
            scripts=scripts,
            do_compress=config.doCompress,
            compress_script=config.compressScript,
            run=config.run,
            force_update=config.forceUpdateRunScripts,
        )


if __name__ == "__main__":
    main()
