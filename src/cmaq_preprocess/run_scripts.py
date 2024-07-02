"""Autogenerate run scripts for the CCTM, BCON and ICON, as well as higher-level run scripts"""

import datetime
import os
import subprocess

from cmaq_preprocess.utils import compress_nc_file, replace_and_write


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
