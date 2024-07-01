"""Autogenerate run scripts for the CCTM, BCON and ICON, as well as higher-level run scripts"""

import datetime
import os
import subprocess

from cmaq_preprocess.utils import compress_nc_file, replace_and_write


def prepare_bcon_run_scripts(
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


def prepare_template_bcon_files(
    date: datetime.date,
    domains,
    ctm_dir,
    met_dir,
    cmaq_dir,
    simulation_name,
    mech,
    grid_names,
    mcip_suffix,
    scripts,
    force_update: bool,
):
    """Prepare template BC files using BCON

    Args:
        date: the dates in question (list of datetime objects)
        domains: list of which domains should be run?
        ctm_dir: base directory for the CCTM inputs and outputs
        met_dir: base directory for the MCIP output
        cmaq_dir: base directory for the CMAQ model
        simulation_name: name of the simulation, appears in some filenames
        mech: name of chemical mechanism to appear in filenames
        grid_names: list of MCIP map projection names (one per domain)
        mcip_suffix: Suffix for the MCIP output files
        scripts: dictionary of scripts, including an entry with the key 'bconRun'
        force_update: Boolean (True/False) for whether we should update the output if it already exists

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
        mcipdir = f"{met_dir}/{yyyymmdd_dashed}/{domain}"
        grid = grid_names[idomain]
        outfile = f"template_bcon_profile_{mech}_{domain}.nc"
        outpath = f"{ctm_dir}/{outfile}"
        outputFiles[idomain] = outpath
        if os.path.exists(outpath):
            if force_update:
                ## BCON does not like it if the destination file exits
                os.remove(outpath)
            else:
                continue
        ##
        ## adjust BCON script
        outBconFile = f"{ctm_dir}/run.bcon"
        ##
        subsBcon = [
            [
                "source TEMPLATE/config.cmaq",
                f"source {cmaq_dir}/scripts/config.cmaq",
            ],
            ["set BC = TEMPLATE", f"set BC = {inputType}"],
            ["set DATE = TEMPLATE", f"set DATE = {yyyyjjj}"],
            ["set CFG      = TEMPLATE", f"set CFG      = {simulation_name}"],
            ["set MECH     = TEMPLATE", f"set MECH     = {mech}"],
            ["setenv GRID_NAME TEMPLATE", f"setenv GRID_NAME {grid}"],
            [
                "setenv GRIDDESC TEMPLATE/GRIDDESC",
                f"setenv GRIDDESC {mcipdir}/GRIDDESC",
            ],
            [
                "setenv LAYER_FILE TEMPLATE/METCRO3D_TEMPLATE",
                f"setenv LAYER_FILE {mcipdir}/METCRO3D_{mcip_suffix[idomain]}",
            ],
            ["setenv OUTDIR TEMPLATE", f"setenv OUTDIR {ctm_dir}"],
            ["setenv OUTFILE TEMPLATE", f"setenv OUTFILE {outfile}"],
        ]
        ##
        print(f"Prepare BCON script for domain = {domain}")
        replace_and_write(scripts["bconRun"]["lines"], outBconFile, subsBcon)
        os.chmod(outBconFile, 0o0744)
        ##
        print("Run BCON")
        command_list = [outBconFile]
        process = subprocess.Popen(command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (output, err) = process.communicate()
        exit_code = process.wait()
        if output.decode().find("Program  BCON completed successfully") < 0:
            print(outBconFile)
            print("exit_code = ", exit_code)
            print("err =", err.decode())
            print("output =", output.decode())
            raise RuntimeError("failure in bcon")
        print("Compress the output file")
        filename = f"{ctm_dir}/{outfile}"
        compress_nc_file(filename)
        outputFiles[idomain] = filename
    ##

    return outputFiles


def prepare_main_run_script(
    dates,
    domains,
    ctm_dir,
    cmaq_dir,
    scripts,
    do_compress,
    compress_script,
    run,
    force_update,
):
    """Setup the higher-level run-script

    Args:
        dates: the dates in question (list of datetime objects)
        domains: list of which domains should be run?
        ctm_dir: base directory for the CCTM inputs and outputs
        cmaq_dir: base directory for the CMAQ model
        scripts: dictionary of scripts, including an entry with the key 'cmaqRun'
        do_compress: Boolean (True/False) for whether the output should be compressed to
            netCDF4 during the simulation
        compress_script: script to find and compress netCDF3 to netCDF4
        run: name of the simulation, appears in some filenames
        force_update: Boolean (True/False) for whether we should update the output if it already exists

    Returns:
        Nothing
    """

    ##
    outfile = "runCMAQ.sh"
    outpath = f"{ctm_dir}/{outfile}"
    if os.path.exists(outpath) and (not force_update):
        return
    ##
    substitutions_cmaq = [
        ["STDATE=TEMPLATE", "STDATE={}".format(dates[0].strftime("%Y%m%d"))],
        ["ENDATE=TEMPLATE", "ENDATE={}".format(dates[-1].strftime("%Y%m%d"))],
        ["domains=(TEMPLATE)", "domains=({})".format(" ".join(domains))],
        ["cmaqDir=TEMPLATE", f"cmaqDir={cmaq_dir}"],
        ["ctmDir=TEMPLATE", f"ctmDir={ctm_dir}"],
        ["doCompress=TEMPLATE", f"doCompress={str(do_compress).lower()}"],
        ["run=TEMPLATE", f"run={run}"],
        ["compressScript=TEMPLATE", f"compressScript={compress_script}"],
    ]
    ##
    print("Prepare the global CMAQ run script")
    replace_and_write(scripts["cmaqRun"]["lines"], outpath, substitutions_cmaq)
    os.chmod(outpath, 0o0744)
    return


def prepare_template_icon_files(
    date: datetime.date,
    domains,
    ctm_dir,
    met_dir,
    cmaq_dir,
    simulation_name,
    mech,
    grid_names,
    mcip_suffix,
    scripts,
    force_update,
):
    """Prepare template IC files using ICON

    Args:
        date: the dates in question
        domains: list of which domains should be run?
        ctm_dir: base directory for the CCTM inputs and outputs
        met_dir: base directory for the MCIP output
        cmaq_dir: base directory for the CMAQ model
        simulation_name: name of the simulation, appears in some filenames
        mech: name of chemical mechanism to appear in filenames
        grid_names: list of MCIP map projection names (one per domain)
        mcip_suffix: Suffix for the MCIP output files
        scripts: dictionary of scripts, including an entry with the key 'iconRun'
        force_update: Boolean (True/False) for whether we should update the output if it already exists

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
        mcipdir = f"{met_dir}/{yyyymmdd_dashed}/{domain}"
        grid = grid_names[idomain]
        outfile = f"template_icon_profile_{mech}_{domain}.nc"
        outpath = f"{ctm_dir}/{outfile}"
        outputFiles[idomain] = outpath
        if os.path.exists(outpath):
            if force_update:
                ## ICON does not like it if the destination file exists
                os.remove(outpath)
            else:
                continue
        ##
        ## adjust ICON script
        outIconFile = f"{ctm_dir}/run.icon"
        ##
        subsIcon = [
            [
                "source TEMPLATE/config.cmaq",
                f"source {cmaq_dir}/scripts/config.cmaq",
            ],
            ["set IC = TEMPLATE", f"set IC = {inputType}"],
            ["set DATE = TEMPLATE", f"set DATE = {yyyyjjj}"],
            ["set CFG      = TEMPLATE", f"set CFG      = {simulation_name}"],
            ["set MECH     = TEMPLATE", f"set MECH     = {mech}"],
            ["setenv GRID_NAME TEMPLATE", f"setenv GRID_NAME {grid}"],
            [
                "setenv GRIDDESC TEMPLATE/GRIDDESC",
                f"setenv GRIDDESC {mcipdir}/GRIDDESC",
            ],
            [
                "setenv LAYER_FILE TEMPLATE/METCRO3D_TEMPLATE",
                f"setenv LAYER_FILE {mcipdir}/METCRO3D_{mcip_suffix[idomain]}",
            ],
            ["setenv OUTDIR TEMPLATE", f"setenv OUTDIR {ctm_dir}"],
            ["setenv OUTFILE TEMPLATE", f"setenv OUTFILE {outfile}"],
        ]
        ##
        print(f"Prepare ICON script for domain = {domain}")
        replace_and_write(scripts["iconRun"]["lines"], outIconFile, subsIcon)
        os.chmod(outIconFile, 0o0744)
        ##
        print("Run ICON")
        command_list = [outIconFile]
        process = subprocess.Popen(command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
        filename = f"{ctm_dir}/{outfile}"
        compress_nc_file(filename)
    ##
    return outputFiles
