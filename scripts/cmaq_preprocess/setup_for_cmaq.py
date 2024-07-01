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

from cmaq_preprocess import utils
from cmaq_preprocess.cams import interpolateFromCAMSToCmaqGrid
from cmaq_preprocess.mcip import runMCIP
from cmaq_preprocess.mcip_preparation import (
    checkInputMetAndOutputFolders,
    getMcipGridNames,
)
from cmaq_preprocess.read_config_cmaq import CMAQConfig, load_cmaq_config
from cmaq_preprocess.run_scripts import (
    prepareBconRunScripts,
    prepareCctmRunScripts,
    prepareMainRunScript,
    prepareTemplateBconFiles,
    prepareTemplateIconFiles,
)


def main(setup_cmaq: CMAQConfig):
    # define date range
    ndates = (setup_cmaq.endDate - setup_cmaq.startDate).days + 1
    dates = [setup_cmaq.startDate + datetime.timedelta(days=d) for d in range(ndates)]

    # read in the template run-scripts
    scripts = utils.loadScripts(scripts=setup_cmaq.scripts)

    # create output destinations, if need be:
    print(
        "Check that input meteorology files are provided and create output destinations (if need be)"
    )
    mcipOuputFound = checkInputMetAndOutputFolders(
        setup_cmaq.ctmDir, setup_cmaq.metDir, dates, setup_cmaq.domains
    )
    print("\t... done")

    if (not mcipOuputFound) or setup_cmaq.forceUpdateMcip:
        runMCIP(
            dates=dates,
            domains=setup_cmaq.domains,
            metDir=setup_cmaq.metDir,
            wrfDir=setup_cmaq.wrfDir,
            geoDir=setup_cmaq.geoDir,
            ProgDir=setup_cmaq.MCIPdir,
            APPL=setup_cmaq.scenarioTag,
            CoordName=setup_cmaq.mapProjName,
            GridName=setup_cmaq.gridName,
            scripts=scripts,
            compressWithNco=True,
            fix_simulation_start_date=True,
            fix_truelat2=False,
            truelat2=None,
            wrfRunName=None,
            doArchiveWrf=False,
            add_qsnow=setup_cmaq.add_qsnow,
        )

    # extract some parameters about the MCIP setup
    CoordNames, GridNames, APPL = getMcipGridNames(setup_cmaq.metDir, dates, setup_cmaq.domains)

    if setup_cmaq.prepareICandBC:
        # prepare the template boundary condition concentration files
        # from profiles using BCON
        templateBconFiles = prepareTemplateBconFiles(
            date=dates[0],
            domains=setup_cmaq.domains,
            ctmDir=setup_cmaq.ctmDir,
            metDir=setup_cmaq.metDir,
            CMAQdir=setup_cmaq.CMAQdir,
            CFG=setup_cmaq.run,
            mech=setup_cmaq.mechCMAQ,
            GridNames=GridNames,
            mcipsuffix=APPL,
            scripts=scripts,
            forceUpdate=setup_cmaq.forceUpdateICandBC,
        )
        # prepare the template initial condition concentration files
        # from profiles using ICON
        templateIconFiles = prepareTemplateIconFiles(
            date=dates[0],
            domains=setup_cmaq.domains,
            ctmDir=setup_cmaq.ctmDir,
            metDir=setup_cmaq.metDir,
            CMAQdir=setup_cmaq.CMAQdir,
            CFG=setup_cmaq.run,
            mech=setup_cmaq.mechCMAQ,
            GridNames=GridNames,
            mcipsuffix=APPL,
            scripts=scripts,
            forceUpdate=setup_cmaq.forceUpdateICandBC,
        )
        # use the template initial and boundary condition concentration
        # files and populate them with values from MOZART output
        interpolateFromCAMSToCmaqGrid(
            dates,
            setup_cmaq.domains,
            setup_cmaq.mech,
            setup_cmaq.inputCAMSFile,
            templateIconFiles,
            templateBconFiles,
            setup_cmaq.metDir,
            setup_cmaq.ctmDir,
            GridNames,
            mcipsuffix=APPL,
            forceUpdate=setup_cmaq.forceUpdateICandBC,
            bias_correct=setup_cmaq.CAMSToCmaqBiasCorrect,
        )

    if setup_cmaq.prepareRunScripts:
        print("Prepare ICON, BCON and CCTM run scripts")
        # prepare the scripts for CCTM
        prepareCctmRunScripts(
            dates=dates,
            domains=setup_cmaq.domains,
            ctmDir=setup_cmaq.ctmDir,
            metDir=setup_cmaq.metDir,
            CMAQdir=setup_cmaq.CMAQdir,
            CFG=setup_cmaq.run,
            mech=setup_cmaq.mech,
            mechCMAQ=setup_cmaq.mechCMAQ,
            GridNames=GridNames,
            mcipsuffix=APPL,
            scripts=scripts,
            EXEC=setup_cmaq.cctmExec,
            SZpath=setup_cmaq.ctmDir,
            nhours=setup_cmaq.nhoursPerRun,
            printFreqHours=setup_cmaq.printFreqHours,
            forceUpdate=setup_cmaq.forceUpdateRunScripts,
        )
        # prepare the scripts for BCON
        prepareBconRunScripts(
            sufadjname=setup_cmaq.sufadj,
            dates=dates,
            domains=setup_cmaq.domains,
            ctmDir=setup_cmaq.ctmDir,
            metDir=setup_cmaq.metDir,
            CMAQdir=setup_cmaq.CMAQdir,
            CFG=setup_cmaq.run,
            mech=setup_cmaq.mech,
            mechCMAQ=setup_cmaq.mechCMAQ,
            GridNames=GridNames,
            mcipsuffix=APPL,
            scripts=scripts,
            forceUpdate=setup_cmaq.forceUpdateRunScripts,
        )
        # prepare the main run script
        prepareMainRunScript(
            dates=dates,
            domains=setup_cmaq.domains,
            ctmDir=setup_cmaq.ctmDir,
            CMAQdir=setup_cmaq.CMAQdir,
            scripts=scripts,
            doCompress=setup_cmaq.doCompress,
            compressScript=setup_cmaq.compressScript,
            run=setup_cmaq.run,
            forceUpdate=setup_cmaq.forceUpdateRunScripts,
        )


if __name__ == "__main__":
    config_file: str = "config/cmaq/config.docker.json"
    setup_cmaq = load_cmaq_config(config_file)

    main(setup_cmaq)
