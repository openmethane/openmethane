#
# Copyright 2016 University of Melbourne.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import datetime
import glob
import os
import subprocess
import time

import openmethane.fourdvar.util.date_handle as dt
import openmethane.fourdvar.util.file_handle as fh
import openmethane.fourdvar.util.netcdf_handle as ncf
from openmethane.fourdvar.params import (
    cmaq_config,
    date_defn,
    template_defn,
)
from openmethane.util.logger import get_logger

logger = get_logger(__name__)


def parse_env_dict(env_dict, date):
    """Convert date patterns into values.

    input: dictionary (envvar_name: pattern_value), dt.date
    output: dictionary (envvar_name: actual_value).

    notes: all names and values must be strings
    """
    parsed = {}

    for name, value in env_dict.items():
        try:
            parsed_value = dt.replace_date(value, date)

            # Remove empty strings from environment which are killing CMAQ multiprocessing
            if value != "":
                parsed[name] = parsed_value
        except Exception:
            logger.exception(f"failed parsing {name}: {value}")
            raise
    return parsed


def setup_run():
    """Setup all the constant environment variables."""
    env_dict = {
        "NPCOL_NPROW": f"{cmaq_config.npcol} {cmaq_config.nprow}",
        "IOAPI_LOG_WRITE": "T" if cmaq_config.ioapi_logging else "F",
        "CTM_MAXSYNC": str(cmaq_config.maxsync),
        "CTM_MINSYNC": str(cmaq_config.minsync),
        "CTM_PT3DEMIS": "Y" if cmaq_config.pt3demis else "N",
        "KZMIN": "Y" if cmaq_config.kzmin else "N",
        "FL_ERR_STOP": "T" if cmaq_config.fl_err_stop else "F",
        "PROMPTFLAG": "T" if cmaq_config.promptflag else "F",
        "EMISDATE": cmaq_config.emisdate,
        "CTM_STDATE": cmaq_config.stdate,
        "CTM_STTIME": "".join([f"{i:02d}" for i in cmaq_config.sttime]),
        "CTM_RUNLEN": "".join([f"{i:02d}" for i in cmaq_config.runlen]),
        "CTM_TSTEP": "".join([f"{i:02d}" for i in cmaq_config.tstep]),
    }

    if str(cmaq_config.emis_lays).strip().lower() == "template":
        fname = dt.replace_date(template_defn.emis, date_defn.start_date)
        emlays = int(ncf.get_attr(fname, "NLAYS"))
        env_dict["CTM_EMLAYS"] = str(emlays)
    else:
        env_dict["CTM_EMLAYS"] = str(cmaq_config.emis_lays)

    if str(cmaq_config.conc_out_lays).strip().lower() == "template":
        conclays = int(ncf.get_attr(template_defn.conc, "NLAYS"))
        env_dict["CONC_BLEV_ELEV"] = f"1 {conclays}"
    else:
        env_dict["CONC_BLEV_ELEV"] = str(cmaq_config.conc_out_lays)

    if str(cmaq_config.avg_conc_out_lays).strip().lower() == "template":
        conclays = int(ncf.get_attr(template_defn.conc, "NLAYS"))
        env_dict["ACONC_BLEV_ELEV"] = f"1 {conclays}"
    else:
        env_dict["ACONC_BLEV_ELEV"] = str(cmaq_config.avg_conc_out_lays)

    if str(cmaq_config.conc_spcs).strip().lower() == "template":
        concspcs = str(ncf.get_attr(template_defn.conc, "VAR-LIST"))
        env_dict["CONC_SPCS"] = " ".join(concspcs.split())
    else:
        env_dict["CONC_SPCS"] = str(cmaq_config.conc_spcs)

    if str(cmaq_config.avg_conc_spcs).strip().lower() == "template":
        concspcs = str(ncf.get_attr(template_defn.conc, "VAR-LIST"))
        env_dict["AVG_CONC_SPCS"] = " ".join(concspcs.split())
    else:
        env_dict["AVG_CONC_SPCS"] = str(cmaq_config.avg_conc_spcs)

    # Ensure the directory for the checkpoint files already exists
    fh.ensure_path(cmaq_config.chk_path)

    env_dict["ADJ_CHEM_CHK"] = cmaq_config.chem_chk + " -v"
    env_dict["ADJ_VDIFF_CHK"] = cmaq_config.vdiff_chk + " -v"
    env_dict["ADJ_AERO_CHK"] = cmaq_config.aero_chk + " -v"
    env_dict["ADJ_CPL_CHK"] = cmaq_config.cpl_chk + " -v"
    env_dict["ADJ_HA_RHOJ_CHK"] = cmaq_config.ha_rhoj_chk + " -v"
    env_dict["ADJ_VA_RHOJ_CHK"] = cmaq_config.va_rhoj_chk + " -v"
    env_dict["ADJ_HADV_CHK"] = cmaq_config.hadv_chk + " -v"
    env_dict["ADJ_VADV_CHK"] = cmaq_config.vadv_chk + " -v"
    env_dict["ADJ_EMIS_CHK"] = cmaq_config.emis_chk + " -v"
    env_dict["ADJ_EMIST_CHK"] = cmaq_config.emist_chk + " -v"
    env_dict["GRIDDESC"] = cmaq_config.griddesc
    env_dict["GRID_NAME"] = cmaq_config.gridname
    env_dict["DEPV_TRAC_1"] = cmaq_config.depv_trac
    # env_dict['OCEAN_1'] = cmaq_config.ocean_file
    env_dict["EMIS_1"] = cmaq_config.emis_file
    env_dict["BNDY_GASC_1"] = cmaq_config.bcon_file
    env_dict["BNDY_AERO_1"] = cmaq_config.bcon_file
    env_dict["BNDY_NONR_1"] = cmaq_config.bcon_file
    env_dict["BNDY_TRAC_1"] = cmaq_config.bcon_file
    env_dict["GRID_DOT_2D"] = cmaq_config.grid_dot_2d
    env_dict["GRID_CRO_2D"] = cmaq_config.grid_cro_2d
    env_dict["MET_CRO_2D"] = cmaq_config.met_cro_2d
    env_dict["MET_CRO_3D"] = cmaq_config.met_cro_3d
    env_dict["MET_DOT_3D"] = cmaq_config.met_dot_3d
    env_dict["MET_BDY_3D"] = cmaq_config.met_bdy_3d
    env_dict["LAYER_FILE"] = cmaq_config.layerfile
    env_dict["XJ_DATA"] = cmaq_config.xj_data
    env_dict["CTM_CONC_1"] = cmaq_config.conc_file + " -v"
    env_dict["A_CONC_1"] = cmaq_config.avg_conc_file + " -v"
    env_dict["S_CGRID"] = cmaq_config.last_grid_file + " -v"
    env_dict["CTM_DRY_DEP_1"] = cmaq_config.drydep_file + " -v"
    env_dict["CTM_WET_DEP_1"] = cmaq_config.wetdep1_file + " -v"
    env_dict["CTM_WET_DEP_2"] = cmaq_config.wetdep2_file + " -v"
    env_dict["CTM_SSEMIS_1"] = cmaq_config.ssemis_file + " -v"
    env_dict["CTM_VIS_1"] = cmaq_config.aerovis_file + " -v"
    env_dict["CTM_DIAM_1"] = cmaq_config.aerodiam_file + " -v"
    env_dict["CTM_IPR_1"] = cmaq_config.ipr1_file + " -v"
    env_dict["CTM_IPR_2"] = cmaq_config.ipr2_file + " -v"
    env_dict["CTM_IPR_3"] = cmaq_config.ipr3_file + " -v"
    env_dict["CTM_IRR_1"] = cmaq_config.irr1_file + " -v"
    env_dict["CTM_IRR_2"] = cmaq_config.irr2_file + " -v"
    env_dict["CTM_IRR_3"] = cmaq_config.irr3_file + " -v"
    env_dict["CTM_RJ_1"] = cmaq_config.rj1_file + " -v"
    env_dict["CTM_RJ_2"] = cmaq_config.rj2_file + " -v"
    return env_dict


def build_cmd(executable: str, stdout_filename: str) -> str:
    """
    Creates the command to run the executable.

    If more than one processor is to be used (as determined by the product of `npcol` and `nprow`),
    `mpirun` will be used to execute the CMAQ binary.

    Parameters
    ----------
    executable
        Binary to be executed
    """
    run_cmd = cmaq_config.cmd_preamble
    if int(cmaq_config.npcol) != 1 or int(cmaq_config.nprow) != 1:
        # use mpi
        # run_cmd += f"mpirun -np {int(cmaq_config.npcol) * int(cmaq_config.nprow)} "

        # write stdout and stderr to a file per-node for debugging
        #  -outfile-pattern=prefix.%r-%h.stdout
        #  -errfile-pattern=prefix.%r-%h.stderr
        run_cmd += f"mpirun -np {int(cmaq_config.npcol) * int(cmaq_config.nprow)} -errfile-pattern={stdout_filename}.%r-%h.stderr "
    run_cmd += executable

    return run_cmd


def run_cmaq(
    executable: str,
    env_dict: dict[str, str],
    template_stdout_filename: str,
    date: datetime.date,
) -> subprocess.CompletedProcess:
    """
    Runs a forward or backward run of CMAQ

    Parameters
    ----------
    executable
        File path of the binary to be executed
    env_dict
        Environment variables to be provided to the subprocess

        The current environment will be merged with these additional variables.
    template_stdout_filename
        Template for the filename of the stdout log
    date
        Date that is being executed

    Raises
    ------
    ValueError
        If the process fails for any reason.
        In that case, the stdout and the CMAQ log are logged.

    Returns
    -------
    Information about the completed process
    """
    stdout_filename = dt.replace_date(template_stdout_filename, date)
    fh.ensure_path(stdout_filename, inc_file=True)

    cmd = build_cmd(executable, stdout_filename)
    logger.debug(f"Running {cmd} for {date.strftime('%Y%m%d')}")

    environment = {**os.environ, **env_dict}

    # This is a workaround for the fact that CMAQ does not handle empty environment variables
    # `env_dict` has likely already been cleaned which is why a warning is logged in this case
    for k in list(environment.keys()):
        if environment[k] == "":
            logger.warning(f"Empty environment variable found: {k}")
            del environment[k]

    t0 = time.time()

    # The command is run in the current directory
    # The environment is set to the values in env_dict
    # TODO: Evaluate whether the current directory for the subprocess should be the `run-cmaq`
    # folder instead.
    res = subprocess.run(
        cmd,
        shell=True,
        executable="/bin/csh",
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    t_elapsed = time.time() - t0

    logger.debug(f"execution completed in {t_elapsed:.3}s")

    with open(stdout_filename, "w") as stdout_fh:
        stdout_fh.write(res.stdout)

    if res.returncode != 0:
        msg = f"{executable} failed for {date.strftime('%Y%m%d')}"
        logger.error(msg)

        logger.error(f"environment: {dict(sorted(environment.items()))}")
        logger.error(f"stdout: {res.stdout}")
        logger.error(f"stderr: {res.stderr}")

        if os.path.exists(env_dict["LOGFILE"]):
            with open(env_dict["LOGFILE"]) as f:
                logger.error(f"CMAQ log file: {f.read()}")
        else:
            logger.error("Log file could not be found")

        raise ValueError(msg)
    return res


def run_fwd_single(date: datetime.date, is_first: bool) -> None:
    """Run cmaq fwd for a single day.

    input: dt.date, Boolean (is this day the first of the model)
    """
    env_dict = setup_run()

    env_dict["PERTCOLS"] = cmaq_config.pertcols
    env_dict["PERTROWS"] = cmaq_config.pertrows
    env_dict["PERTLEVS"] = cmaq_config.pertlevs
    env_dict["PERTSPCS"] = cmaq_config.pertspcs
    env_dict["PERTDELT"] = cmaq_config.pertdelt
    env_dict["CTM_APPL"] = cmaq_config.fwd_appl
    env_dict["CTM_XFIRST_OUT"] = cmaq_config.fwd_xfirst_file
    env_dict["LOGFILE"] = cmaq_config.fwd_logfile
    env_dict["FLOOR_FILE"] = cmaq_config.floor_file
    env_dict["CTM_PROGNAME"] = cmaq_config.fwd_prog

    if is_first is True:
        env_dict["INIT_GASC_1"] = cmaq_config.icon_file
        env_dict["INIT_AERO_1"] = cmaq_config.icon_file
        env_dict["INIT_NONR_1"] = cmaq_config.icon_file
        env_dict["INIT_TRAC_1"] = cmaq_config.icon_file
        env_dict["CTM_XFIRST_IN"] = ""
    else:
        prev_grid = dt.move_tag(cmaq_config.last_grid_file, -1)
        prev_xfirst = dt.move_tag(cmaq_config.fwd_xfirst_file, -1)
        env_dict["INIT_GASC_1"] = prev_grid
        env_dict["INIT_AERO_1"] = prev_grid
        env_dict["INIT_NONR_1"] = prev_grid
        env_dict["INIT_TRAC_1"] = prev_grid
        env_dict["CTM_XFIRST_IN"] = prev_xfirst

    env_dict = parse_env_dict(env_dict, date)

    run_cmaq(
        cmaq_config.fwd_prog,
        env_dict=env_dict,
        template_stdout_filename=cmaq_config.fwd_stdout_log,
        date=date,
    )


def run_bwd_single(date, is_first):
    """Run cmaq bwd for a single day.

    input: dt.date, Boolean (is this the first time called)
    output: None.
    """
    env_dict = setup_run()

    env_dict["CTM_APPL"] = cmaq_config.bwd_appl
    env_dict["CTM_XFIRST_OUT"] = cmaq_config.bwd_xfirst_file
    env_dict["CTM_XFIRST_IN"] = cmaq_config.fwd_xfirst_file
    env_dict["LOGFILE"] = cmaq_config.bwd_logfile
    env_dict["CTM_PROGNAME"] = cmaq_config.bwd_prog
    env_dict["CHK_PATH"] = cmaq_config.chk_path
    env_dict["INIT_GASC_1"] = cmaq_config.last_grid_file + " -v"
    env_dict["INIT_AERO_1"] = cmaq_config.last_grid_file + " -v"
    env_dict["INIT_NONR_1"] = cmaq_config.last_grid_file + " -v"
    env_dict["INIT_TRAC_1"] = cmaq_config.last_grid_file + " -v"
    env_dict["CTM_CONC_FWD"] = cmaq_config.conc_file + " -v"
    env_dict["CTM_CGRID_FWD"] = cmaq_config.last_grid_file + " -v"
    env_dict["ADJ_LGRID"] = cmaq_config.conc_sense_file + " -v"
    env_dict["ADJ_LGRID_EM"] = cmaq_config.emis_sense_file + " -v"
    env_dict["ADJ_LGRID_EM_SF"] = cmaq_config.emis_scale_sense_file + " -v"
    env_dict["ADJ_FORCE"] = cmaq_config.force_file

    if cmaq_config.sense_sync is True:
        env_dict["ADJ_LGRID_FREQ"] = "SYNC_STEP"
    else:
        env_dict["ADJ_LGRID_FREQ"] = "OUTPUT_STEP"

    if str(cmaq_config.force_lays).strip().lower() == "template":
        frclays = int(ncf.get_attr(template_defn.force, "NLAYS"))
        env_dict["NLAYS_FRC"] = str(frclays)
    else:
        env_dict["NLAYS_FRC"] = str(cmaq_config.force_lays)

    if str(cmaq_config.sense_emis_lays).strip().lower() == "template":
        emsensl = int(ncf.get_attr(template_defn.sense_emis, "NLAYS"))
        env_dict["CTM_EMSENSL"] = str(emsensl)
    else:
        env_dict["CTM_EMSENSL"] = str(cmaq_config.sense_emis_lays)

    if is_first is not True:
        prev_conc = dt.move_tag(cmaq_config.conc_sense_file, 1)
        prev_emis = dt.move_tag(cmaq_config.emis_sense_file, 1)
        prev_scale = dt.move_tag(cmaq_config.emis_scale_sense_file, 1)
        env_dict["INIT_LGRID_1"] = prev_conc
        env_dict["INIT_EM_1"] = prev_emis
        env_dict["INIT_EM_SF_1"] = prev_scale

    env_dict = parse_env_dict(env_dict, date)

    run_cmaq(
        cmaq_config.bwd_prog,
        date=date,
        template_stdout_filename=cmaq_config.bwd_stdout_log,
        env_dict=env_dict,
    )


def clear_local_logs():
    """Delete logfiles CMAQ puts in cwd.
    input: None
    output: None.
    """
    # delete every file that matches a pattern in cmaq_config.cwd_logs
    for file_pattern in cmaq_config.cwd_logs:
        file_list = glob.glob(file_pattern)
        for file_name in file_list:
            full_file_name = os.path.realpath(file_name)
            if os.path.isfile(full_file_name):
                os.remove(full_file_name)


def run_fwd():
    """Run cmaq fwd from current config.
    input: None
    output: None.
    """
    isfirst = True
    for cur_date in dt.get_datelist():
        run_fwd_single(cur_date, isfirst)
        isfirst = False
        clear_local_logs()


def run_bwd():
    """Run cmaq bwd from current config.
    input: None
    output: None.
    """
    isfirst = True
    for cur_date in dt.get_datelist()[::-1]:
        run_bwd_single(cur_date, isfirst)
        isfirst = False
        clear_local_logs()


def _cleanup(file_list: list[str]):
    """
    Deletes a list of files.

    Each file may contain dates, which are replaced with wildcards before deletion.

    Parameters
    ----------
    file_list
        List of templated files to be deleted
    """
    clear_local_logs()

    all_tags = dt.tag_map.keys()
    for pat_name in file_list:
        name = pat_name
        # Loop over the different date tags and replace them with a wildcard
        for t in all_tags:
            name = name.replace(t, "*")
        for fname in glob.glob(name):
            if os.path.isfile(fname):
                os.remove(fname)


def wipeout_bwd():
    """Delete all files created by a backward run of cmaq."""
    _cleanup(cmaq_config.wipeout_bwd_list)


def wipeout_fwd():
    """Delete all files created by a forward run of cmaq."""

    _cleanup(cmaq_config.wipeout_fwd_list)
