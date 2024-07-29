"""Autogenerate run scripts for the CCTM, BCON and ICON, as well as higher-level run scripts"""

import datetime
import os
import pathlib

from cmaq_preprocess.utils import compress_nc_file, replace_and_write, run_command


def prepare_template_bcon_files(
    date: datetime.datetime,
    domains: list[str],
    ctm_dir: str,
    met_dir: str,
    cmaq_dir: str,
    CFG: str,
    mech: str,
    GridNames: list[str],
    mcipsuffix: list[str],
    scripts,
    forceUpdate: bool,
) -> list[pathlib.Path]:
    """Prepare template BC files using BCON

    Args:
        dates: the dates in question (list of datetime objects)
        domains: list of which domains should be run?
        ctm_dir: base directory for the CCTM inputs and outputs
        met_dir: base directory for the MCIP output
        cmaq_dir: base directory for the CMAQ model
        CFG: name of the simulation, appears in some filenames
        mech: name of chemical mechanism to appear in filenames
        GridNames: list of MCIP map projection names (one per domain)
        mcipsuffix: Suffix for the MCIP output files
        scripts: dictionary of scripts, including an entry with the key 'bconRun'
        forceUpdate: If True, update the output even if it already exists

    Returns:
        list of the template BCON files (one per domain)
    """
    met_dir = pathlib.Path(met_dir)
    ctm_dir = pathlib.Path(ctm_dir)

    yyyyjjj = date.strftime("%Y%j")
    yyyymmdd_dashed = date.strftime("%Y-%m-%d")

    output_files = []
    input_type = "profile"

    for idomain, domain in enumerate(domains):
        mcipdir = met_dir / yyyymmdd_dashed / domain
        grid = GridNames[idomain]
        outfile = f"template_bcon_profile_{mech}_{domain}.nc"

        subs_bcon = [
            [
                "source TEMPLATE/config.cmaq",
                f"source {cmaq_dir}/scripts/config.cmaq",
            ],
            ["set BC = TEMPLATE", f"set BC = {input_type}"],
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
            ["setenv OUTDIR TEMPLATE", f"setenv OUTDIR {ctm_dir}"],
            ["setenv OUTFILE TEMPLATE", f"setenv OUTFILE {outfile}"],
        ]

        output_files.append(
            _run(
                "bcon",
                outfile,
                ctm_dir,
                domain,
                scripts["bconRun"]["lines"],
                subs_bcon,
                log_prefix="bcon-template",
                force_update=forceUpdate,
            )
        )

    return output_files


def prepare_template_icon_files(
    date: datetime.datetime,
    domains: list[str],
    ctm_dir: str,
    met_dir: str,
    cmaq_dir: str,
    CFG: str,
    mech: str,
    GridNames: list[str],
    mcipsuffix: list[str],
    scripts,
    forceUpdate: bool,
) -> list[pathlib.Path]:
    """Prepare template IC files using ICON

    Args:
        dates: the dates in question (list of datetime objects)
        domains: list of which domains should be run?
        ctm_dir: base directory for the CCTM inputs and outputs
        met_dir: base directory for the MCIP output
        cmaq_dir: base directory for the CMAQ model
        CFG: name of the simulation, appears in some filenames
        mech: name of chemical mechanism to appear in filenames
        GridNames: list of MCIP map projection names (one per domain)
        mcipsuffix: Suffix for the MCIP output files
        scripts: dictionary of scripts, including an entry with the key 'iconRun'
        forceUpdate: If True, update the output even if it already exists

    Returns:
        list of the template ICON files (one per domain)
    """
    met_dir = pathlib.Path(met_dir)
    ctm_dir = pathlib.Path(ctm_dir)

    yyyyjjj = date.strftime("%Y%j")
    yyyymmdd_dashed = date.strftime("%Y-%m-%d")

    output_files = []

    for idomain, domain in enumerate(domains):
        mcip_dir = met_dir / yyyymmdd_dashed / domain
        grid = GridNames[idomain]

        input_type = "profile"
        outfile = f"template_icon_profile_{mech}_{domain}.nc"

        subs_icon = [
            [
                "source TEMPLATE/config.cmaq",
                f"source {cmaq_dir}/scripts/config.cmaq",
            ],
            ["set IC = TEMPLATE", f"set IC = {input_type}"],
            ["set DATE = TEMPLATE", f"set DATE = {yyyyjjj}"],
            ["set CFG      = TEMPLATE", f"set CFG      = {CFG}"],
            ["set MECH     = TEMPLATE", f"set MECH     = {mech}"],
            ["setenv GRID_NAME TEMPLATE", f"setenv GRID_NAME {grid}"],
            [
                "setenv GRIDDESC TEMPLATE/GRIDDESC",
                f"setenv GRIDDESC {mcip_dir}/GRIDDESC",
            ],
            [
                "setenv LAYER_FILE TEMPLATE/METCRO3D_TEMPLATE",
                f"setenv LAYER_FILE {mcip_dir}/METCRO3D_{mcipsuffix[idomain]}",
            ],
            ["setenv OUTDIR TEMPLATE", f"setenv OUTDIR {ctm_dir}"],
            ["setenv OUTFILE TEMPLATE", f"setenv OUTFILE {outfile}"],
        ]

        output_files.append(
            _run(
                "icon",
                outfile,
                ctm_dir,
                domain,
                scripts["iconRun"]["lines"],
                subs_icon,
                log_prefix="icon-template",
                force_update=forceUpdate,
            )
        )

    return output_files


def _run(
    executable: str,
    output_filename: str,
    ctm_dir: pathlib.Path,
    domain: str,
    input_script: list[str],
    substitutions: list[list[str]],
    log_prefix: str | None = None,
    force_update: bool = False,
):
    """
    Run BCON/ICON

    Substo
    Parameters
    ----------
    executable
    output_filename
    ctm_dir
    domain
    input_script
    substitutions
    log_prefix
    force_update

    Returns
    -------

    """
    out_data_path = ctm_dir / output_filename

    if out_data_path.exists() and force_update:
        ## BCON does not like it if the destination file exits
        os.remove(out_data_path)

    out_run_path = ctm_dir / f"run.{executable}"
    ##
    print(f"Prepare BCON script for domain = {domain}")
    replace_and_write(input_script, out_run_path, substitutions)
    os.chmod(out_run_path, 0o0744)

    print(f"Run {executable}")
    stdout, stderr = run_command([str(out_run_path)], log_prefix=log_prefix, verbose=True)

    if stdout.find(f"Program  {executable.upper()} completed successfully") < 0:
        raise RuntimeError(f"failure in {executable}")

    print("Compress the output file")
    compress_nc_file(out_data_path)

    return out_data_path
