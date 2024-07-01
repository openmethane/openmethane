"""Autogenerate run scripts for the CCTM, BCON and ICON, as well as higher-level run scripts"""

import os
import subprocess

from cmaq_preprocess.utils import compressNCfile, replace_and_write


def prepareCctmRunScripts(
    dates,
    domains,
    ctmDir,
    metDir,
    CMAQdir,
    CFG,
    mech,
    mechCMAQ,
    GridNames,
    mcipsuffix,
    scripts,
    EXEC,
    SZpath,
    forceUpdate,
    nhours=24,
    printFreqHours=1,
):
    """Prepare one run script for CCTM per domain per day

    Args:
        dates: the dates in question (list of datetime objects)
        domains: list of which domains should be run?
        ctmDir: base directory for the CCTM inputs and outputs
        metDir: base directory for the MCIP output
        CMAQdir: base directory for the CMAQ model
        CFG: name of the simulation, appears in some filenames
        mech: name of chemical mechanism to appear in filenames
        mechCMAQ: name of chemical mechanism given to CMAQ
        GridNames: list of MCIP map projection names (one per domain)
        mcipsuffix: Suffix for the MCIP output fileso
        scripts: dictionary of scripts, including an entry with the key 'cctmRun'
        EXEC: The name of the CCTM executable
        SZpath: Folder containing the surfzone files
        forceUpdate: Boolean (True/False) for whether we should update the output if it already exists
        nhours: number of hours to run at a time (24 means run a whole day at once)
        printFreqHours: frequency of the CMAQ output (1 means hourly output) - so far it is not set up to run for sub-hourly

    Returns:
        Nothing

    """

    for idate, date in enumerate(dates):
        yyyyjjj = date.strftime("%Y%j")
        yyyymmdd = date.strftime("%Y%m%d")
        yyyy = date.strftime("%Y")
        yy = date.strftime("%y")
        mm = date.strftime("%m")
        dd = date.strftime("%d")
        yyyymmdd_dashed = date.strftime("%Y-%m-%d")
        hhmmss = date.strftime("%H%M%S")
        duration = f"{nhours:02d}0000"
        if printFreqHours >= 1:
            tstep = f"{printFreqHours:02d}0000"
        else:
            raise RuntimeError(
                "argument printFreqHours currently not configured for sub-hourly output..."
            )
        ##
        if idate != 0:
            lastdate = dates[idate - 1]
            lastyyyymmdd = lastdate.strftime("%Y%m%d")
            lastyyyymmdd_dashed = lastdate.strftime("%Y-%m-%d")
        ##
        for idomain, domain in enumerate(domains):
            mcipdir = f"{metDir}/{yyyymmdd_dashed}/{domain}"
            chemdir = f"{ctmDir}/{yyyymmdd_dashed}/{domain}"
            chemdatedir = f"{ctmDir}/{yyyymmdd_dashed}"
            outCctmFile = f"{chemdir}/run.cctm_{domain}_{yyyymmdd}"
            if os.path.exists(outCctmFile) and not forceUpdate:
                continue
            ##
            grid = GridNames[idomain]
            if idate == 0:
                ICONdir = f"{ctmDir}/{yyyymmdd_dashed}/{domain}"
                ICfile = f"ICON.{domain}.{grid}.{mech}.nc"
            else:
                lastCTM_APPL = f"{CFG}_{lastyyyymmdd}"
                ICONdir = f"{ctmDir}/{lastyyyymmdd_dashed}/{domain}"
                ICfile = f"{EXEC.strip()}.CGRID.{lastCTM_APPL.strip()}"
            ##
            BCfile = f"BCON.{domain}.{grid}.{mech}.nc"

            EMISfile = f"Allmerged_emis_{yyyymmdd_dashed}_{domain}.nc"
            # print("emisfile= ",EMISfile)

            subsCctm = [
                [
                    "source TEMPLATE/config.cmaq",
                    f"source {CMAQdir}/scripts/config.cmaq",
                ],
                ["set CFG = TEMPLATE", f"set CFG = {CFG}"],
                ["set MECH = TEMPLATE", f"set MECH = {mechCMAQ}"],
                ["set STDATE = TEMPLATE", f"set STDATE = {yyyyjjj}"],
                ["set STTIME = TEMPLATE", f"set STTIME = {hhmmss}"],
                ["set NSTEPS = TEMPLATE", f"set NSTEPS = {duration}"],
                ["set TSTEP = TEMPLATE", f"set TSTEP = {tstep}"],
                ["set YEAR = TEMPLATE", f"set YEAR = {yyyy}"],
                ["set YR = TEMPLATE", f"set YR = {yy}"],
                ["set MONTH = TEMPLATE", f"set MONTH = {mm}"],
                ["set DAY = TEMPLATE", f"set DAY = {dd}"],
                ["setenv GRID_NAME TEMPLATE", f"setenv GRID_NAME {grid}"],
                [
                    "setenv GRIDDESC TEMPLATE/GRIDDESC",
                    f"setenv GRIDDESC {mcipdir}/GRIDDESC",
                ],
                ["set ICpath = TEMPLATE", f"set ICpath = {ICONdir}"],
                ["set BCpath = TEMPLATE", f"set BCpath = {chemdir}"],
                ["set EMISpath = TEMPLATE", f"set EMISpath = {chemdir}"],
                ["set METpath = TEMPLATE", f"set METpath = {mcipdir}"],
                ["set JVALpath = TEMPLATE", f"set JVALpath = {chemdatedir}"],
                ["set LUpath = TEMPLATE", f"set LUpath = {mcipdir}"],
                ["set SZpath = TEMPLATE", f"set SZpath = {SZpath}"],
                [
                    "setenv OCEAN_1 $SZpath/TEMPLATE",
                    f"setenv OCEAN_1 $SZpath/surfzone_{domain}.nc",
                ],
                ["set OUTDIR = TEMPLATE", f"set OUTDIR = {chemdir}"],
                ["set ICFILE = TEMPLATE", f"set ICFILE = {ICfile}"],
                ["set BCFILE = TEMPLATE", f"set BCFILE = {BCfile}"],
                ["set EXTN = TEMPLATE", f"set EXTN = {mcipsuffix[idomain]}"],
                ["set EMISfile = TEMPLATE", f"set EMISfile = {EMISfile}"],
            ]
            ##
            ## adjust CCTM script
            print(
                "Prepare CMAQ script for date = {} and domain = {}".format(
                    date.strftime("%Y%m%d"), domain
                )
            )
            replace_and_write(scripts["cctmRun"]["lines"], outCctmFile, subsCctm)
            print(outCctmFile)
            os.chmod(outCctmFile, 0o0744)


def prepareBconRunScripts(
    sufadjname,
    dates,
    domains,
    ctmDir,
    metDir,
    CMAQdir,
    CFG,
    mech,
    mechCMAQ,
    GridNames,
    mcipsuffix,
    scripts,
    forceUpdate,
):
    """Prepare run scripts for BCON, one per domain per day

    Args:
        dates: the dates in question (list of datetime objects)
        domains: list of which domains should be run?
        ctmDir: base directory for the CCTM inputs and outputs
        metDir: base directory for the MCIP output
        CMAQdir: base directory for the CMAQ model
        CFG: name of the simulation, appears in some filenames
        mech: name of chemical mechanism to appear in filenames
        mechCMAQ: name of chemical mechanism given to CMAQ
        GridNames: list of MCIP map projection names (one per domain)
        mcipsuffix: Suffix for the MCIP output files
        scripts: dictionary of scripts, including an entry with the key 'bconRun'
        forceUpdate: Boolean (True/False) for whether we should update the output if it already exists

    Returns:
        Nothing
    """

    inputType = "m3conc"
    for idate, date in enumerate(dates):
        yyyyjjj = date.strftime("%Y%j")
        yyyymmdd = date.strftime("%Y%m%d")
        yyyymmdd_dashed = date.strftime("%Y-%m-%d")

        for idomain, domain in enumerate(domains):
            mcipdir = f"{metDir}/{yyyymmdd_dashed}/{domain}"
            chemdir = f"{ctmDir}/{yyyymmdd_dashed}/{domain}"
            grid = GridNames[idomain]
            ##
            ## adjust BCON script
            if idomain != 0:
                lastmcipdir = f"{ctmDir}/{yyyymmdd_dashed}/{domains[idomain - 1]}"

                outBconFile = f"{chemdir}/run.bcon_{domain}_{yyyymmdd}"
                if os.path.exists(outBconFile) and not forceUpdate:
                    continue
                ##
                outfile = f"BCON.{domain}.{grid}.{mech}.nc"
                input3Dconfile = (
                    f"{ctmDir}/{mech}_{domains[idomain - 1]}_{sufadjname}/CONC.{yyyymmdd}"
                )
                MetCro3dCrs = f"{lastmcipdir}/METCRO3D_{mcipsuffix[idomain - 1]}"
                MetCro3dFin = f"{mcipdir}/METCRO3D_{mcipsuffix[idomain]}"
                subsBcon = [
                    [
                        "source TEMPLATE/config.cmaq",
                        f"source {CMAQdir}/scripts/config.cmaq",
                    ],
                    ["set BC = TEMPLATE", f"set BC = {inputType}"],
                    ["set DATE = TEMPLATE", f"set DATE = {yyyyjjj}"],
                    ["set CFG      = TEMPLATE", f"set CFG      = {CFG}"],
                    ["set MECH     = TEMPLATE", f"set MECH     = {mechCMAQ}"],
                    ["setenv GRID_NAME TEMPLATE", f"setenv GRID_NAME {grid}"],
                    [
                        "setenv GRIDDESC TEMPLATE/GRIDDESC",
                        f"setenv GRIDDESC {mcipdir}/GRIDDESC",
                    ],
                    [
                        "setenv LAYER_FILE TEMPLATE/METCRO3D_TEMPLATE",
                        f"setenv LAYER_FILE {MetCro3dFin}",
                    ],
                    ["setenv OUTDIR TEMPLATE", f"setenv OUTDIR {chemdir}"],
                    ["setenv OUTFILE TEMPLATE", f"setenv OUTFILE {outfile}"],
                    [
                        "setenv CTM_CONC_1 TEMPLATE",
                        f"setenv CTM_CONC_1 {input3Dconfile}",
                    ],
                    [
                        "setenv MET_CRO_3D_CRS TEMPLATE",
                        f"setenv MET_CRO_3D_CRS {MetCro3dCrs}",
                    ],
                    [
                        "setenv MET_CRO_3D_FIN TEMPLATE",
                        f"setenv MET_CRO_3D_FIN {MetCro3dFin}",
                    ],
                ]
                ##
                print(
                    "Prepare BCON script for date = {} and domain = {}".format(
                        date.strftime("%Y%m%d"), domain
                    )
                )
                replace_and_write(scripts["bconRun"]["lines"], outBconFile, subsBcon)
                os.chmod(outBconFile, 0o0744)


def prepareTemplateBconFiles(
    date,
    domains,
    ctmDir,
    metDir,
    CMAQdir,
    CFG,
    mech,
    GridNames,
    mcipsuffix,
    scripts,
    forceUpdate,
):
    """Prepare template BC files using BCON

    Args:
        dates: the dates in question (list of datetime objects)
        domains: list of which domains should be run?
        ctmDir: base directory for the CCTM inputs and outputs
        metDir: base directory for the MCIP output
        CMAQdir: base directory for the CMAQ model
        CFG: name of the simulation, appears in some filenames
        mech: name of chemical mechanism to appear in filenames
        GridNames: list of MCIP map projection names (one per domain)
        mcipsuffix: Suffix for the MCIP output files
        scripts: dictionary of scripts, including an entry with the key 'bconRun'
        forceUpdate: Boolean (True/False) for whether we should update the output if it already exists

    Returns:
        list of the template BCON files (one per domain)
    """

    ##
    yyyyjjj = date.strftime("%Y%j")
    # yyyymmdd = date.strftime("%Y%m%d")
    yyyymmdd_dashed = date.strftime("%Y-%m-%d")
    ##
    ndom = len(domains)
    outputFiles = [""] * ndom
    inputType = "profile"
    for idomain, domain in enumerate(domains):
        mcipdir = f"{metDir}/{yyyymmdd_dashed}/{domain}"
        grid = GridNames[idomain]
        outfile = f"template_bcon_profile_{mech}_{domain}.nc"
        outpath = f"{ctmDir}/{outfile}"
        outputFiles[idomain] = outpath
        if os.path.exists(outpath):
            if forceUpdate:
                ## BCON does not like it if the destination file exits
                os.remove(outpath)
            else:
                continue
        ##
        ## adjust BCON script
        outBconFile = f"{ctmDir}/run.bcon"
        ##
        subsBcon = [
            [
                "source TEMPLATE/config.cmaq",
                f"source {CMAQdir}/scripts/config.cmaq",
            ],
            ["set BC = TEMPLATE", f"set BC = {inputType}"],
            ["set DATE = TEMPLATE", f"set DATE = {yyyyjjj}"],
            ["set CFG      = TEMPLATE", f"set CFG      = {CFG}"],
            ["set MECH     = TEMPLATE", f"set MECH     = {mech}"],
            ["setenv GRID_NAME TEMPLATE", f"setenv GRID_NAME {grid}"],
            [
                "setenv GRIDDESC TEMPLATE/GRIDDESC",
                f"setenv GRIDDESC {mcipdir}/GRIDDESC",
            ],
            [
                "setenv LAYER_FILE TEMPLATE/METCRO3D_TEMPLATE",
                f"setenv LAYER_FILE {mcipdir}/METCRO3D_{mcipsuffix[idomain]}",
            ],
            ["setenv OUTDIR TEMPLATE", f"setenv OUTDIR {ctmDir}"],
            ["setenv OUTFILE TEMPLATE", f"setenv OUTFILE {outfile}"],
        ]
        ##
        print(f"Prepare BCON script for domain = {domain}")
        replace_and_write(scripts["bconRun"]["lines"], outBconFile, subsBcon)
        os.chmod(outBconFile, 0o0744)
        ##
        print("Run BCON")
        commandList = [outBconFile]
        process = subprocess.Popen(commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (output, err) = process.communicate()
        exit_code = process.wait()
        try:
            if output.decode().find("Program  BCON completed successfully") < 0:
                print(outBconFile)
                print("exit_code = ", exit_code)
                print("err =", err.decode())
                print("output =", output.decode())
                raise RuntimeError("failure in bcon")
        except Exception:
            raise
        ##
        print("Compress the output file")
        filename = f"{ctmDir}/{outfile}"
        compressNCfile(filename)
        outputFiles[idomain] = filename
    ##

    return outputFiles


def prepareMainRunScript(
    dates,
    domains,
    ctmDir,
    CMAQdir,
    scripts,
    doCompress,
    compressScript,
    run,
    forceUpdate,
):
    """Setup the higher-level run-script

    Args:
        dates: the dates in question (list of datetime objects)
        domains: list of which domains should be run?
        ctmDir: base directory for the CCTM inputs and outputs
        CMAQdir: base directory for the CMAQ model
        scripts: dictionary of scripts, including an entry with the key 'cmaqRun'
        doCompress: Boolean (True/False) for whether the output should be compressed to netCDF4 during the simulation
        compressScript: script to find and compress netCDF3 to netCDF4
        run: name of the simulation, appears in some filenames
        forceUpdate: Boolean (True/False) for whether we should update the output if it already exists

    Returns:
        Nothing
    """

    ##
    outfile = "runCMAQ.sh"
    outpath = f"{ctmDir}/{outfile}"
    if os.path.exists(outpath) and (not forceUpdate):
        return
    ##
    subsCMAQ = [
        ["STDATE=TEMPLATE", "STDATE={}".format(dates[0].strftime("%Y%m%d"))],
        ["ENDATE=TEMPLATE", "ENDATE={}".format(dates[-1].strftime("%Y%m%d"))],
        ["domains=(TEMPLATE)", "domains=({})".format(" ".join(domains))],
        ["cmaqDir=TEMPLATE", f"cmaqDir={CMAQdir}"],
        ["ctmDir=TEMPLATE", f"ctmDir={ctmDir}"],
        ["doCompress=TEMPLATE", f"doCompress={str(doCompress).lower()}"],
        ["run=TEMPLATE", f"run={run}"],
        ["compressScript=TEMPLATE", f"compressScript={compressScript}"],
    ]
    ##
    print("Prepare the global CMAQ run script")
    replace_and_write(scripts["cmaqRun"]["lines"], outpath, subsCMAQ)
    os.chmod(outpath, 0o0744)
    return


def prepareTemplateIconFiles(
    date,
    domains,
    ctmDir,
    metDir,
    CMAQdir,
    CFG,
    mech,
    GridNames,
    mcipsuffix,
    scripts,
    forceUpdate,
):
    """Prepare template IC files using ICON

    Args:
        dates: the dates in question (list of datetime objects)
        domains: list of which domains should be run?
        ctmDir: base directory for the CCTM inputs and outputs
        metDir: base directory for the MCIP output
        CMAQdir: base directory for the CMAQ model
        CFG: name of the simulation, appears in some filenames
        mech: name of chemical mechanism to appear in filenames
        GridNames: list of MCIP map projection names (one per domain)
        mcipsuffix: Suffix for the MCIP output files
        scripts: dictionary of scripts, including an entry with the key 'iconRun'
        forceUpdate: Boolean (True/False) for whether we should update the output if it already exists

    Returns:
        list of the template ICON files (one per domain)
    """
    ##
    yyyyjjj = date.strftime("%Y%j")
    # yyyymmdd = date.strftime("%Y%m%d")
    yyyymmdd_dashed = date.strftime("%Y-%m-%d")

    ndom = len(domains)
    outputFiles = [""] * ndom
    inputType = "profile"
    for idomain, domain in enumerate(domains):
        mcipdir = f"{metDir}/{yyyymmdd_dashed}/{domain}"
        grid = GridNames[idomain]
        outfile = f"template_icon_profile_{mech}_{domain}.nc"
        outpath = f"{ctmDir}/{outfile}"
        outputFiles[idomain] = outpath
        if os.path.exists(outpath):
            if forceUpdate:
                ## ICON does not like it if the destination file exists
                os.remove(outpath)
            else:
                continue
        ##
        ## adjust ICON script
        outIconFile = f"{ctmDir}/run.icon"
        ##
        subsIcon = [
            [
                "source TEMPLATE/config.cmaq",
                f"source {CMAQdir}/scripts/config.cmaq",
            ],
            ["set IC = TEMPLATE", f"set IC = {inputType}"],
            ["set DATE = TEMPLATE", f"set DATE = {yyyyjjj}"],
            ["set CFG      = TEMPLATE", f"set CFG      = {CFG}"],
            ["set MECH     = TEMPLATE", f"set MECH     = {mech}"],
            ["setenv GRID_NAME TEMPLATE", f"setenv GRID_NAME {grid}"],
            [
                "setenv GRIDDESC TEMPLATE/GRIDDESC",
                f"setenv GRIDDESC {mcipdir}/GRIDDESC",
            ],
            [
                "setenv LAYER_FILE TEMPLATE/METCRO3D_TEMPLATE",
                f"setenv LAYER_FILE {mcipdir}/METCRO3D_{mcipsuffix[idomain]}",
            ],
            ["setenv OUTDIR TEMPLATE", f"setenv OUTDIR {ctmDir}"],
            ["setenv OUTFILE TEMPLATE", f"setenv OUTFILE {outfile}"],
        ]
        ##
        print(f"Prepare ICON script for domain = {domain}")
        replace_and_write(scripts["iconRun"]["lines"], outIconFile, subsIcon)
        os.chmod(outIconFile, 0o0744)
        ##
        print("Run ICON")
        commandList = [outIconFile]
        process = subprocess.Popen(commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (output, err) = process.communicate()
        exit_code = process.wait()
        if output.decode().find("Program  ICON completed successfully") < 0:
            print(outIconFile)
            print("exit_code = ", exit_code)
            print("err =", err)
            print("output =", output)
            raise RuntimeError("failure in icon")
        ##
        print("Compress the output file")
        filename = f"{ctmDir}/{outfile}"
        compressNCfile(filename)
    ##
    return outputFiles
