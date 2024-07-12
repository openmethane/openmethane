"""Autogenerate run scripts for the CCTM, BCON and ICON, as well as higher-level run scripts"""

import os
import subprocess

from cmaq_preprocess.utils import compress_nc_file, replace_and_write


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
    forceUpdate: bool,
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
        forceUpdate: If True, update the output even if it already exists

    Returns:
        list of the template BCON files (one per domain)
    """

    ##
    yyyyjjj = date.strftime("%Y%j")
    yyyymmdd_dashed = date.strftime("%Y-%m-%d")
    ##
    ndom = len(domains)
    outputFiles = [""] * ndom
    inputType = "profile"
    for idomain, domain in enumerate(domains):
        mcipdir = f"{metDir}/{yyyymmdd_dashed}/{domain}"
        grid = GridNames[idomain]
        outfile = f"template_bcon_profile_{mech}_{domain}.nc"
        outpath = os.path.join(ctmDir, outfile)
        outputFiles[idomain] = outpath
        if os.path.exists(outpath):
            if forceUpdate:
                ## BCON does not like it if the destination file exits
                os.remove(outpath)
            else:
                continue
        ##
        ## adjust BCON script
        outBconFile = os.path.join(ctmDir, "run.bcon")
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

        if output.decode().find("Program  BCON completed successfully") < 0:
            print(outBconFile)
            print("exit_code = ", exit_code)
            print("err =", err.decode())
            print("output =", output.decode())
            raise RuntimeError("failure in bcon")

        print("Compress the output file")
        filename = f"{ctmDir}/{outfile}"
        compress_nc_file(filename)
        outputFiles[idomain] = filename

    return outputFiles


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
    forceUpdate: bool,
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
        forceUpdate: If True, update the output even if it already exists

    Returns:
        list of the template ICON files (one per domain)
    """
    ##
    yyyyjjj = date.strftime("%Y%j")
    yyyymmdd_dashed = date.strftime("%Y-%m-%d")

    ndom = len(domains)
    outputFiles = [""] * ndom
    inputType = "profile"
    for idomain, domain in enumerate(domains):
        mcipdir = f"{metDir}/{yyyymmdd_dashed}/{domain}"
        grid = GridNames[idomain]
        outfile = f"template_icon_profile_{mech}_{domain}.nc"
        outpath = os.path.join(ctmDir, outfile)
        outputFiles[idomain] = outpath
        if os.path.exists(outpath):
            if forceUpdate:
                ## ICON does not like it if the destination file exists
                os.remove(outpath)
            else:
                continue
        ##
        ## adjust ICON script
        outIconFile = os.path.join(ctmDir, "run.icon")

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
        compress_nc_file(filename)
    ##
    return outputFiles
