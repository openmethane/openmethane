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
from cmaq_preprocess.cams import interpolateFromCAMSToCmaqGrid
from cmaq_preprocess.mcip import runMCIP
from cmaq_preprocess.mcip_preparation import (
    checkInputMetAndOutputFolders,
    getMcipGridNames,
)
from cmaq_preprocess.read_config_cmaq import CMAQConfig, load_cmaq_config
from cmaq_preprocess.run_scripts import (
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
    mcip_output_found = checkInputMetAndOutputFolders(
        config.ctmDir, config.metDir, dates, config.domains
    )
    print("\t... done")

    if (not mcip_output_found) or config.forceUpdate:
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
            boundary_trim=config.boundary_trim,
        )

    # extract some parameters about the MCIP setup
    coord_names, grid_names, mcip_suffix = getMcipGridNames(config.metDir, dates, config.domains)

    if config.prepareICandBC:
        # prepare the template boundary condition concentration files
        # from profiles using BCON
        template_bcon_files = prepare_template_bcon_files(
            date=dates[0],
            domains=config.domains,
            ctm_dir=config.ctmDir,
            met_dir=config.metDir,
            cmaq_dir=config.CMAQdir,
            CFG=config.run,
            mech=config.mech,
            GridNames=grid_names,
            mcipsuffix=mcip_suffix,
            scripts=scripts,
            forceUpdate=config.forceUpdate,
        )
        # prepare the template initial condition concentration files
        # from profiles using ICON
        template_icon_files = prepare_template_icon_files(
            date=dates[0],
            domains=config.domains,
            ctm_dir=config.ctmDir,
            met_dir=config.metDir,
            cmaq_dir=config.CMAQdir,
            CFG=config.run,
            mech=config.mech,
            GridNames=grid_names,
            mcipsuffix=mcip_suffix,
            scripts=scripts,
            forceUpdate=config.forceUpdate,
        )
        # use the template initial and boundary condition concentration
        # files and populate them with values from MOZART output
        interpolateFromCAMSToCmaqGrid(
            dates,
            config.domains,
            config.mech,
            config.inputCAMSFile,
            template_icon_files,
            template_bcon_files,
            config.metDir,
            config.ctmDir,
            grid_names,
            mcipsuffix=mcip_suffix,
            forceUpdate=config.forceUpdate,
            bias_correct=config.CAMSToCmaqBiasCorrect,
        )


if __name__ == "__main__":
    main()
