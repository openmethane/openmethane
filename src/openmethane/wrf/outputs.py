"""Where the WRF step's output goes, and when a day's output is complete.

This layout is the contract with MCIP: for each day, in
`<output_path>/<YYYYMMDD>00/`, one averaged file per domain per hour, from 00Z
on the day to 00Z on the next day inclusive, named
`WRFOUT_<dNN>_<YYYY-MM-DD>T<HHMM>Z.nc`. Raw `wrfout_*` files left beside them
mean averaging didn't finish.
"""

import datetime
import pathlib

from openmethane.wrf.geometry import DomainSet

HOURS_PER_DAY_OUTPUT = 25
"""Averaged files per domain per day: 00Z to the next day's 00Z, inclusive"""


def day_folder(output_path: pathlib.Path, day: datetime.date) -> pathlib.Path:
    """The folder holding one day's output."""
    return output_path / day.strftime("%Y%m%d00")


def averaged_file_name(domain_id: str, time: datetime.datetime) -> str:
    """The name of one averaged hour of output, such as WRFOUT_d01_2022-12-07T0100Z.nc."""
    return f"WRFOUT_{domain_id}_{time.strftime('%Y-%m-%dT%H%M')}Z.nc"


def expected_files(domains: DomainSet, day: datetime.date) -> list[str]:
    """Names of every averaged file a complete day has, for every domain."""
    midnight = datetime.datetime.combine(day, datetime.time())
    return [
        averaged_file_name(domain.id, midnight + datetime.timedelta(hours=hour))
        for domain in domains
        for hour in range(HOURS_PER_DAY_OUTPUT)
    ]


def missing_files(output_path: pathlib.Path, domains: DomainSet, day: datetime.date) -> list[str]:
    """
    What stops a day's output from being complete.

    Returns
    -------
    The expected averaged files that are absent, then any raw `wrfout_*` files
    present. Empty when the day is complete.
    """
    folder = day_folder(output_path, day)
    missing = [name for name in expected_files(domains, day) if not (folder / name).exists()]
    raw = sorted(path.name for path in folder.glob("wrfout_*")) if folder.is_dir() else []
    return missing + raw


def is_complete(output_path: pathlib.Path, domains: DomainSet, day: datetime.date) -> bool:
    """Whether every domain has all of a day's averaged files, and no raw files remain."""
    return not missing_files(output_path, domains, day)
