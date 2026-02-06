"""Autogenerate run scripts for the CCTM, BCON and ICON, as well as higher-level run scripts"""

import datetime
import os
import pathlib
from typing import Literal

from openmethane.cmaq_preprocess.read_config_cmaq import Domain
from openmethane.cmaq_preprocess.utils import compress_nc_file, nested_dir, replace_and_write, run_command


def prepare_template_bcon_files(
    date: datetime.date,
    domain: Domain,
    ctm_dir: pathlib.Path,
    met_dir: pathlib.Path,
    mech: str,
    cmaq_bin_dir: pathlib.Path,
    bcon_run_path: pathlib.Path,
    forceUpdate: bool,
) -> pathlib.Path:
    """
    Prepare template BC files using BCON.

    :param date: date to generate the template for
    :param domain: domain of interest
    :param ctm_dir: base directory for the CCTM inputs and outputs
    :param met_dir: directory containing MCIP output
    :param mech: name of chemical mechanism BCON was compiled with
    :param cmaq_bin_dir: base directory containing CMAQ binaries / builds
    :param bcon_run_path: path to the run.bcon script
    :param forceUpdate: if True, replace existing output if present
    :return: path to the template BCON file
    """
    input_type = "profile"
    mcip_dir = nested_dir(domain, date, met_dir)
    outfile = f"template_bcon_profile_{mech}_{domain.id}.nc"
    out_data_path = ctm_dir / outfile

    environment = {
        "M3DATA": mcip_dir,
        "CMAQ_MECH": mech,
        "DOMAIN_GRID": domain.mcip_suffix,
        "BIN_PATH": cmaq_bin_dir,
        "BCON_MODTYPE": input_type,
        "BCON_DATE": date.strftime("%Y%j"),
        "MCIP_DIR": mcip_dir,
        "OUTPUT_DIR": ctm_dir,
        "OUTPUT_FILE": outfile,
    }

    if out_data_path.exists():
        if forceUpdate:
            ## ICON/BCON do not like it if the destination file exits
            os.remove(out_data_path)
        else:
            raise FileExistsError(
                f"Existing file {out_data_path} found, use forceUpdate to overwrite"
            )

    return _run(
        bcon_run_path,
        environment=environment,
        out_data_path=out_data_path,
        log_prefix="bcon-template",
    )


def prepare_template_icon_files(
    date: datetime.date,
    domain: Domain,
    ctm_dir: pathlib.Path,
    met_dir: pathlib.Path,
    mech: str,
    cmaq_bin_dir: pathlib.Path,
    icon_run_path: pathlib.Path,
    forceUpdate: bool,
) -> pathlib.Path:
    """
    Prepare template IC files using ICON.

    :param date: date to generate the template for
    :param domain: domain of interest
    :param ctm_dir: base directory for the CCTM inputs and outputs
    :param met_dir: directory containing MCIP output
    :param mech: name of chemical mechanism BCON was compiled with
    :param cmaq_bin_dir: base directory containing CMAQ binaries / builds
    :param icon_run_path: path to the run.icon script
    :param forceUpdate: if True, replace existing output if present
    :return: path to the template ICON file
    """
    input_type = "profile"
    mcip_dir = nested_dir(domain, date, met_dir)
    outfile = f"template_icon_profile_{mech}_{domain.id}.nc"
    out_data_path = ctm_dir / outfile

    environment = {
        "M3DATA": mcip_dir,
        "CMAQ_MECH": mech,
        "DOMAIN_GRID": domain.mcip_suffix,
        "BIN_PATH": cmaq_bin_dir,
        "ICON_MODTYPE": input_type,
        "ICON_DATE": date.strftime("%Y%j"),
        "MCIP_DIR": mcip_dir,
        "OUTPUT_DIR": ctm_dir,
        "OUTPUT_FILE": outfile,
    }

    if out_data_path.exists():
        if forceUpdate:
            ## ICON/BCON do not like it if the destination file exits
            os.remove(out_data_path)
        else:
            raise FileExistsError(
                f"Existing file {out_data_path} found, use forceUpdate to overwrite"
            )

    return _run(
        icon_run_path,
        environment=environment,
        out_data_path=out_data_path,
        log_prefix="icon-template",
    )


def _run(
    run_script_path: pathlib.Path,
    out_data_path: pathlib.Path,
    environment: dict[str, str],
    log_prefix: str | None = None,
):
    """

    :param run_script_path: path to the run script, ie "/opt/bin/run.bcon"
    :param out_data_path: path to the expected output file
    :param environment: dict of env variables required by the run script
    :param log_prefix: if provided, used as prefix for log output files
    :return: path to the output file created by the run script
    """
    out_data_path.parent.mkdir(parents=True, exist_ok=True)

    stdout, stderr = run_command(
        run_script_path,
        env_overrides=environment,
        log_prefix=str(out_data_path.parent / log_prefix),
        verbose=True,
    )

    if stdout.find(f"completed successfully") < 0:
        raise RuntimeError(f"failure in {run_script_path}")

    print("Compress the output file")
    compress_nc_file(out_data_path)

    return out_data_path
