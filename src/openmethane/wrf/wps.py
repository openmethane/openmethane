"""Run ungrib and metgrid to put the analyses on the domains' grids.

Runs in a window's working folder, and leaves its met_em files in the met_em
cache, where they are reused by any later run of the same window.
"""

import datetime
import logging
import pathlib

from openmethane.util.process import run_program
from openmethane.wrf.geometry import DomainSet
from openmethane.wrf.install import WrfInstall

logger = logging.getLogger(__name__)

MET_EM_TIME_FORMAT = "%Y-%m-%d_%H:%M:%S"

# Intermediate files ungrib and metgrid leave in the working folder
INTERMEDIATE_PATTERNS = ("ERA:*", "SST:*", "FILE:*", "PFILE:*", "GRIBFILE.*", "fort.*")


class WpsError(RuntimeError):
    """WPS ran but didn't produce what was expected."""


def met_em_name(domain_id: str, time: datetime.datetime) -> str:
    """The name of a met_em file, such as met_em.d01.2022-12-07_00:00:00.nc."""
    return f"met_em.{domain_id}.{time.strftime(MET_EM_TIME_FORMAT)}.nc"


def needed_met_em(domains: DomainSet, times: list[datetime.datetime]) -> list[str]:
    """Names of the met_em files a window needs: every domain at every analysis time."""
    return [met_em_name(domain.id, time) for time in times for domain in domains]


def missing_met_em(
    cache_path: pathlib.Path, domains: DomainSet, times: list[datetime.datetime]
) -> list[str]:
    """The met_em files a window needs that aren't in the cache."""
    return [name for name in needed_met_em(domains, times) if not (cache_path / name).exists()]


def link_into(window_dir: pathlib.Path, source: pathlib.Path, name: str | None = None) -> None:
    """Link a file into the working folder, replacing any link already there."""
    link = window_dir / (name or source.name)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(source)


def run_wps(
    window_dir: pathlib.Path,
    subsets: list[pathlib.Path],
    install: WrfInstall,
    cache_path: pathlib.Path,
    log_dir: pathlib.Path,
) -> list[pathlib.Path]:
    """
    Run link_grib.csh, ungrib and metgrid, and move the met_em files to the cache.

    `namelist.wps` and each domain's `geo_em.dNN.nc` must already be in the
    working folder.

    Parameters
    ----------
    window_dir
        The window's working folder.
    subsets
        The analyses to read, whole.
    install
        Where WPS is.
    cache_path
        The met_em cache.
    log_dir
        Where to write each program's log.

    Returns
    -------
    The met_em files now in the cache.
    """
    _purge(window_dir)
    run_program(
        [install.link_grib, *subsets],
        cwd=window_dir,
        log_path=log_dir / "link_grib.log",
    )
    if not list(window_dir.glob("GRIBFILE.*")):
        raise WpsError(f"link_grib.csh linked no GRIB files in {window_dir}")

    link_into(window_dir, install.fnl_vtable, "Vtable")
    run_program(
        [install.ungrib_exe],
        cwd=window_dir,
        log_path=log_dir / "ungrib.log",
        success_text="Successful completion of ungrib",
    )

    # metgrid looks for its table in ./metgrid/
    (window_dir / "metgrid").mkdir(exist_ok=True)
    link_into(window_dir / "metgrid", install.metgrid_table)
    run_program(
        [install.metgrid_exe],
        cwd=window_dir,
        log_path=log_dir / "metgrid.log",
        success_text="Successful completion of metgrid",
    )

    cache_path.mkdir(parents=True, exist_ok=True)
    moved = []
    for met_em in sorted(window_dir.glob("met_em.*.nc")):
        moved.append(met_em.replace(cache_path / met_em.name))
    if not moved:
        raise WpsError(f"metgrid wrote no met_em files in {window_dir}")
    _purge(window_dir)
    logger.info(f"moved {len(moved)} met_em files to {cache_path}")
    return moved


def _purge(window_dir: pathlib.Path) -> None:
    """Remove intermediate files from an earlier or the current run of WPS."""
    for pattern in INTERMEDIATE_PATTERNS:
        for path in window_dir.glob(pattern):
            if path.is_symlink() or path.is_file():
                path.unlink()
    vtable = window_dir / "Vtable"
    if vtable.is_symlink():
        vtable.unlink()
