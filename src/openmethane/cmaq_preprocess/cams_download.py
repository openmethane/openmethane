"""Download CAMS methane products from the Atmosphere Data Store (ADS)"""

import concurrent.futures
import datetime
import os
import pathlib
import tempfile
import time
import zipfile

import requests
import xarray as xr

from openmethane.util.logger import get_logger

logger = get_logger(__name__)

INVERSION_DATASET = "cams-global-greenhouse-gas-inversion"
INVERSION_DEFAULT_VERSION = "v25r1"

RANGE_CHUNK_BYTES = 32 * 1024 * 1024
RANGE_CONNECTIONS = 16
RANGE_RETRIES = 6
RANGE_BACKOFF_SECONDS = 5


def _download_range(url: str, file_descriptor: int, start: int, end: int):
    """Fetch bytes [start, end] of `url` into the file descriptor at the same offset"""
    for attempt in range(RANGE_RETRIES):
        try:
            response = requests.get(
                url, headers={"Range": f"bytes={start}-{end}"}, timeout=120, stream=True
            )
            response.raise_for_status()
            if response.status_code != 206:
                raise RuntimeError(f"{url} ignored the Range header (HTTP {response.status_code})")
            offset = start
            for block in response.iter_content(chunk_size=1024 * 1024):
                os.pwrite(file_descriptor, block, offset)
                offset += len(block)
            if offset != end + 1:
                raise RuntimeError(f"short read for bytes {start}-{end}: got {offset - start}")
            return
        except (requests.RequestException, RuntimeError) as err:
            if attempt == RANGE_RETRIES - 1:
                raise
            logger.warning(f"retrying bytes {start}-{end} after: {err}")
            time.sleep(RANGE_BACKOFF_SECONDS * 2**attempt)


def download_in_ranges(
    url: str,
    destination: pathlib.Path,
    size: int,
    connections: int = RANGE_CONNECTIONS,
    chunk_bytes: int = RANGE_CHUNK_BYTES,
):
    """Download `url` to `destination` using parallel byte-range requests

    ADS serves a single connection at about 0.3 MB/s, so a 2 GB file takes hours
    when fetched serially.
    """
    ranges = [(start, min(start + chunk_bytes, size) - 1) for start in range(0, size, chunk_bytes)]
    file_descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    try:
        os.ftruncate(file_descriptor, size)
        with concurrent.futures.ThreadPoolExecutor(max_workers=connections) as pool:
            futures = [
                pool.submit(_download_range, url, file_descriptor, start, end)
                for start, end in ranges
            ]
            for future in concurrent.futures.as_completed(futures):
                future.result()
    finally:
        os.close(file_descriptor)


def months_in_range(start: datetime.date, end: datetime.date) -> list[tuple[int, int]]:
    """Calendar months touched by the inclusive date range"""
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def download_inversion(
    start: datetime.date, end: datetime.date, version: str, directory: pathlib.Path
) -> list[pathlib.Path]:
    """Download the global CAMS inversion files for each month in the date range

    Returns one file per month, named `{year}-{month}.nc`, in `directory`.
    """
    return [
        retrieve_inversion_month(year, month, version, directory / f"{year}-{month:02d}.nc")
        for year, month in months_in_range(start, end)
    ]


def retrieve_inversion_month(
    year: int, month: int, version: str, destination: pathlib.Path, client=None
) -> pathlib.Path:
    """Download one month of CAMS inversion CH4 concentration, extracted to a netCDF file

    The ADS delivers a global monthly file as a zip, and cannot subset by area.
    """
    import cdsapi

    client = client or cdsapi.Client()
    request = {
        "variable": "methane",
        "quantity": "concentration",
        "input_observations": "surface_satellite",
        "time_aggregation": "instantaneous",
        "version": version,
        "year": f"{year:04d}",
        "month": f"{month:02d}",
    }
    try:
        result = client.retrieve(INVERSION_DATASET, request)
    except Exception as err:
        raise RuntimeError(
            f"The CAMS inversion {version} has no methane concentration for "
            f"{year:04d}-{month:02d}, or the request failed: {err}. "
            "The inversion adds a year of data roughly once a year; "
            "use CAMS_PRODUCT=eac4 for dates it does not cover yet."
        ) from err

    with tempfile.TemporaryDirectory(dir=destination.parent) as scratch:
        archive = pathlib.Path(scratch) / "inversion.zip"
        logger.info(f"downloading {result.content_length / 1e9:.2f} GB for {year}-{month:02d}")
        download_in_ranges(result.location, archive, result.content_length)
        with zipfile.ZipFile(archive) as archive_zip:
            members = [name for name in archive_zip.namelist() if name.endswith(".nc")]
            if len(members) != 1:
                raise RuntimeError(f"expected one netCDF in the CAMS archive, found {members}")
            extracted = archive_zip.extract(members[0], scratch)
        os.replace(extracted, destination)
    return destination


DOMAIN_PADDING_DEGREES = 3.0
INVERSION_VARIABLES = ["CH4", "ps", "hyam", "hybm"]


def cut_inversion_to_domain(
    monthly_files: list[pathlib.Path],
    domain_file: pathlib.Path,
    start: datetime.date,
    end: datetime.date,
    destination: pathlib.Path,
):
    """Keep only the methane, pressure and domain needed from the global monthly files

    The time axis keeps one step past `end`, because the reader takes the latest
    CAMS step at or before each model time.
    """
    with xr.open_dataset(domain_file) as domain:
        lat_min, lat_max = float(domain.lat.min()), float(domain.lat.max())
        lon_min, lon_max = float(domain.lon.min()), float(domain.lon.max())
    padding = DOMAIN_PADDING_DEGREES
    time_start = datetime.datetime.combine(start, datetime.time())
    time_end = datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time())

    pieces = []
    release = None
    for path in monthly_files:
        with xr.open_dataset(path) as monthly:
            release = monthly.attrs["release"]
            piece = monthly[INVERSION_VARIABLES].sel(
                latitude=slice(lat_min - padding, lat_max + padding),
                longitude=slice(lon_min - padding, lon_max + padding),
                time=slice(time_start, time_end),
            )
            pieces.append(piece.load())
    cut = xr.concat(pieces, dim="time", data_vars="minimal")
    # the source packs CH4 into int16 with a scale and offset specific to each month,
    # which must not be reapplied to the other months
    for variable in cut.variables.values():
        variable.encoding = {}
    cut.attrs.update(
        {
            "title": "CAMS inversion CH4 cut to the Open Methane domain",
            "cams_product": "inversion",
            "cams_release": release,
        }
    )
    cut.to_netcdf(destination)
