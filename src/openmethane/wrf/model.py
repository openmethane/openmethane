"""Run real.exe and wrf.exe under mpirun.

Both are MPI programs that write their progress, and their success line, to
`rsl.out.0000` in the working folder rather than to stdout. So success is
checked there, on top of the exit code.
"""

import logging
import pathlib
import re
import shutil

import netCDF4

from openmethane.util.process import ProgramFailed, run_program
from openmethane.wrf.geometry import DomainSet
from openmethane.wrf.install import WrfInstall

logger = logging.getLogger(__name__)

REAL_SUCCESS = "SUCCESS COMPLETE REAL_EM INIT"
WRF_SUCCESS = "SUCCESS COMPLETE WRF"
RSL_LOG = "rsl.out.0000"
RUN_FILE_PATTERN = re.compile("(DAT|formatted|CAM|asc|TBL|dat|tbl|txt|tr)")
"""WRF data files and tables to link into a run, setup-wrf's `wrf_run_tables_pattern`.
It leaves out the example namelist.input in WRF's run folder."""
REAL_RSL_DIR = "real-rsl"
"""Where real.exe's rsl files are moved, since wrf.exe writes over them"""


def metgrid_levels(met_em: pathlib.Path) -> tuple[int, int]:
    """The atmospheric and soil levels in a met_em file, which real.exe must be told."""
    with netCDF4.Dataset(met_em) as dataset:
        return (
            len(dataset.dimensions["num_metgrid_levels"]),
            len(dataset.dimensions["num_st_layers"]),
        )


def real_outputs(window_dir: pathlib.Path, domains: DomainSet) -> list[pathlib.Path]:
    """The files real.exe writes: boundaries for the outer domain, and each domain's inputs."""
    return [
        window_dir / "wrfbdy_d01",
        *(window_dir / f"wrfinput_{domain.id}" for domain in domains),
        *(window_dir / f"wrflowinp_{domain.id}" for domain in domains),
    ]


def link_run_files(window_dir: pathlib.Path, install: WrfInstall) -> None:
    """Link WRF's data files and tables into the working folder, keeping any already there."""
    for source in sorted(install.run_dir.iterdir()):
        if not RUN_FILE_PATTERN.search(source.name):
            continue
        link = window_dir / source.name
        if not (link.exists() or link.is_symlink()):
            link.symlink_to(source)


def run_real(window_dir: pathlib.Path, install: WrfInstall, log_dir: pathlib.Path) -> None:
    """
    Run real.exe on one rank, to make the initial and boundary conditions.

    `namelist.input`, the window's met_em files and WRF's data files must be in
    the working folder.
    """
    _clear_rsl(window_dir)
    _run_mpi(1, install.real_exe, window_dir, log_dir / "real.log")
    _check_rsl(window_dir, "real.exe", REAL_SUCCESS, log_dir / "real.log")

    real_rsl = window_dir / REAL_RSL_DIR
    if real_rsl.exists():
        shutil.rmtree(real_rsl)
    real_rsl.mkdir()
    for rsl in window_dir.glob("rsl.*"):
        rsl.rename(real_rsl / rsl.name)


def run_wrf(
    window_dir: pathlib.Path, install: WrfInstall, ranks: int, log_dir: pathlib.Path
) -> None:
    """
    Run wrf.exe on `ranks` MPI ranks, then remove its restart files.

    Restart files aren't used, and `restart_interval` is set so long that only
    the final one is written.
    """
    _clear_rsl(window_dir)
    logger.info(f"running wrf.exe on {ranks} ranks")
    _run_mpi(ranks, install.wrf_exe, window_dir, log_dir / "wrf.log")
    _check_rsl(window_dir, "wrf.exe", WRF_SUCCESS, log_dir / "wrf.log")
    for restart in window_dir.glob("wrfrst*"):
        restart.unlink()


def _run_mpi(ranks: int, program: pathlib.Path, cwd: pathlib.Path, log_path: pathlib.Path) -> None:
    """Run a program under mpirun, reporting a failure as the program's rather than mpirun's."""
    try:
        run_program(["mpirun", "-np", str(ranks), program], cwd=cwd, log_path=log_path)
    except ProgramFailed as error:
        raise ProgramFailed(program.name, error.exit_code, error.log_path, error.tail) from error


def _clear_rsl(window_dir: pathlib.Path) -> None:
    """Remove rsl files from an earlier run, so a stale success line can't be read."""
    for rsl in window_dir.glob("rsl.*"):
        rsl.unlink()


def _check_rsl(
    window_dir: pathlib.Path, program: str, success: str, log_path: pathlib.Path
) -> None:
    """Check the first rank's rsl file for the program's success line."""
    rsl = window_dir / RSL_LOG
    text = rsl.read_text(errors="replace") if rsl.exists() else ""
    if success not in text:
        tail = text.splitlines(keepends=True)[-20:]
        raise ProgramFailed(program, 0, rsl if rsl.exists() else log_path, tail, success)
