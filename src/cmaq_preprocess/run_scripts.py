"""Autogenerate run scripts for the CCTM, BCON and ICON, as well as higher-level run scripts"""

import datetime
import os
import pathlib
from typing import Literal

from cmaq_preprocess.read_config_cmaq import Domain
from cmaq_preprocess.utils import compress_nc_file, nested_dir, replace_and_write, run_command


def prepare_template_bcon_files(
    date: datetime.datetime,
    domain: Domain,
    ctm_dir: pathlib.Path,
    met_dir: pathlib.Path,
    cmaq_dir: pathlib.Path,
    mech: str,
    scripts,
    forceUpdate: bool,
) -> pathlib.Path:
    """Prepare template BC files using BCON

    Args:
        date: Date to generate the template for
        domain: Domain to generate the template for
        ctm_dir: base directory for the CCTM inputs and outputs
        met_dir: base directory for the MCIP output
        cmaq_dir: base directory for the CMAQ model
        mech: name of chemical mechanism to appear in filenames
        scripts: dictionary of scripts, including an entry with the key 'bconRun'
        forceUpdate: If True, update the output even if it already exists

    Returns:
        list of the template BCON files (one per domain)
    """
    yyyyjjj = date.strftime("%Y%j")

    input_type = "profile"

    mcipdir = nested_dir(domain, date, met_dir)
    outfile = f"template_bcon_profile_{mech}_{domain.id}.nc"

    subs_bcon = [
        [
            "source TEMPLATE/config.cmaq",
            f'source {cmaq_dir/ "scripts" / "config.cmaq"}',
        ],
        ["set BC = TEMPLATE", f"set BC = {input_type}"],
        ["set DATE = TEMPLATE", f"set DATE = {yyyyjjj}"],
        ["set CFG      = TEMPLATE", f"set CFG      = {domain.scenario_tag}"],
        ["set MECH     = TEMPLATE", f"set MECH     = {mech}"],
        ["setenv GRID_NAME TEMPLATE", f"setenv GRID_NAME {domain.name}"],
        [
            "setenv GRIDDESC TEMPLATE/GRIDDESC",
            f"setenv GRIDDESC {mcipdir}/GRIDDESC",
        ],
        [
            "setenv LAYER_FILE TEMPLATE/METCRO3D_TEMPLATE",
            f"setenv LAYER_FILE {mcipdir}/METCRO3D_{domain.scenario_tag}",
        ],
        ["setenv OUTDIR TEMPLATE", f"setenv OUTDIR {ctm_dir}"],
        ["setenv OUTFILE TEMPLATE", f"setenv OUTFILE {outfile}"],
    ]
    out_data_path = ctm_dir / outfile

    if out_data_path.exists():
        if forceUpdate:
            ## ICON/BCON do not like it if the destination file exits
            os.remove(out_data_path)
        else:
            raise FileExistsError(
                f"Existing file {out_data_path} found, use forceUpdate to overwrite"
            )

    return _run(
        "bcon",
        out_data_path,
        scripts["bconRun"]["lines"],
        subs_bcon,
        log_prefix="bcon-template",
    )


def prepare_template_icon_files(
    date: datetime.datetime,
    domain: Domain,
    ctm_dir: pathlib.Path,
    met_dir: pathlib.Path,
    cmaq_dir: pathlib.Path,
    mech: str,
    scripts,
    forceUpdate: bool,
) -> pathlib.Path:
    """Prepare template IC files using ICON

    Args:
        date: Date to generate the template for
        domain: Domain to generate the template for
        ctm_dir: base directory for the CCTM inputs and outputs
        met_dir: base directory for the MCIP output
        cmaq_dir: base directory for the CMAQ model
        mech: name of chemical mechanism to appear in filenames
        scripts: dictionary of scripts, including an entry with the key 'iconRun'
        forceUpdate: If True, update the output even if it already exists

    Returns:
        list of the template ICON files (one per domain)
    """

    yyyyjjj = date.strftime("%Y%j")

    mcip_dir = nested_dir(domain, date, met_dir)

    input_type = "profile"
    outfile = f"template_icon_profile_{mech}_{domain.id}.nc"

    subs_icon = [
        [
            "source TEMPLATE/config.cmaq",
            f'source {cmaq_dir/ "scripts" / "config.cmaq"}',
        ],
        ["set IC = TEMPLATE", f"set IC = {input_type}"],
        ["set DATE = TEMPLATE", f"set DATE = {yyyyjjj}"],
        ["set CFG      = TEMPLATE", f"set CFG      = {domain.scenario_tag}"],
        ["set MECH     = TEMPLATE", f"set MECH     = {mech}"],
        ["setenv GRID_NAME TEMPLATE", f"setenv GRID_NAME {domain.name}"],
        [
            "setenv GRIDDESC TEMPLATE/GRIDDESC",
            f"setenv GRIDDESC {mcip_dir}/GRIDDESC",
        ],
        [
            "setenv LAYER_FILE TEMPLATE/METCRO3D_TEMPLATE",
            f"setenv LAYER_FILE {mcip_dir}/METCRO3D_{domain.scenario_tag}",
        ],
        ["setenv OUTDIR TEMPLATE", f"setenv OUTDIR {ctm_dir}"],
        ["setenv OUTFILE TEMPLATE", f"setenv OUTFILE {outfile}"],
    ]

    out_data_path = ctm_dir / outfile

    if out_data_path.exists():
        if forceUpdate:
            ## ICON/BCON do not like it if the destination file exits
            os.remove(out_data_path)
        else:
            raise FileExistsError(
                f"Existing file {out_data_path} found, use forceUpdate to overwrite"
            )

    return _run(
        "icon",
        out_data_path,
        scripts["iconRun"]["lines"],
        subs_icon,
        log_prefix="icon-template",
    )


def _run(
    executable: Literal["bcon", "icon"],
    out_data_path: pathlib.Path,
    input_script: list[str],
    substitutions: list[list[str]],
    log_prefix: str | None = None,
):
    """
    Run BCON/ICON

    Substitutes the values in the input script and runs the shell script.

    Parameters
    ----------
    executable
        Name of the executable. Could be either icon or bcon
    out_data_path
        Path to the output file that will be generated as part of this run

        The run script will be created in the same directory.
    input_script
        Collection of lines in the input script
    substitutions
        List of substitutions to make in the input script
    log_prefix
        Prefix to use for the log file

    Returns
    -------
        Output file
    """

    out_run_path = out_data_path.parent / f"run.{executable}"

    print(f"Prepare {executable} script")
    replace_and_write(input_script, out_run_path, substitutions)
    os.chmod(out_run_path, 0o0744)

    print(f"Run {executable}")
    stdout, stderr = run_command([str(out_run_path)], log_prefix=log_prefix, verbose=True)

    if stdout.find(f"Program  {executable.upper()} completed successfully") < 0:
        raise RuntimeError(f"failure in {executable}")

    print("Compress the output file")
    compress_nc_file(out_data_path)

    return out_data_path
