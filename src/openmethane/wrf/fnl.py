"""NCEP GDAS/FNL analyses: which are needed, and fetching them.

WRF is driven by the 0.25° GDAS/FNL analyses (ds083.3, DOI 10.5065/D65Q4T4Z),
one every 6 hours. ungrib reads the global files whole. setup-wrf also cut
them to a box around the domain with wgrib2, but passed the uncut files to
ungrib, so the cut never reached production; using it changes met_em.
"""

import datetime
import pathlib
from collections.abc import Iterable

from openmethane.util.download import fetch_missing

FNL_DATASET_ROOT = "https://data.gdex.ucar.edu/d083003/"
"""Where the analyses are published. Needs no credentials"""

FNL_FIRST_TIME = datetime.datetime(2015, 7, 8)
"""The 0.25° analyses start after this time"""


def fnl_file_name(time: datetime.datetime) -> str:
    """The file name of the analysis at a time."""
    return time.strftime("gdas1.fnl0p25.%Y%m%d%H.f00.grib2")


def fnl_url(time: datetime.datetime, dataset_root: str = FNL_DATASET_ROOT) -> str:
    """
    The URL of the analysis at a time.

    Raises
    ------
    ValueError
        If there is no analysis at that time: they are every 6 hours, from
        after 2015-07-08.
    """
    if time.hour % 6 or time.minute or time.second or time.microsecond:
        raise ValueError(f"FNL analyses are at 00, 06, 12 and 18Z, not {time}")
    if time <= FNL_FIRST_TIME:
        raise ValueError(f"FNL 0.25° analyses start after {FNL_FIRST_TIME}, not {time}")
    return f"{dataset_root.rstrip('/')}/{time.strftime('%Y/%Y%m')}/{fnl_file_name(time)}"


def fetch_analyses(
    times: Iterable[datetime.datetime],
    cache_path: pathlib.Path,
    dataset_root: str = FNL_DATASET_ROOT,
) -> list[pathlib.Path]:
    """
    Download any of the analyses not already in the cache.

    Returns
    -------
    The path of each analysis in the cache, in time order.
    """
    times = sorted(set(times))
    return fetch_missing([fnl_url(time, dataset_root) for time in times], cache_path)
