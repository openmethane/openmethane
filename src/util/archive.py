"""
Helper methods for fetching parts of previous Open Methane results. Primarily
used to load daily data for use in monthly workflows, or re-loading daily data
during re-processing.
"""

import datetime
import pathlib
import subprocess

from util.logger import get_logger

logger = get_logger(__name__)


def monthly(
    daily_s3_bucket: str,
    start_date: datetime.date,
    end_date: datetime.date,
    domain_name: str,
    local_path: pathlib.Path,
):
    """
    Sync a subset of the daily output for a range of dates into the working
    folder for the current execution. This daily data is needed for the monthly
    workflow.
    """
    for date in _date_range(start_date, end_date):  # this is inclusive of END_DATE
        destination_path = pathlib.Path(
            local_path,
            domain_name,
            "daily",
            str(date.year),
            f"{date.month:02}",
            f"{date.day:02}",
        )

        daily_root = _get_daily_archive_path(daily_s3_bucket, domain_name, date)

        for remote_path in [
            "input",
            "cmaq",
            "mcip",
        ]:
            _s3_sync_fetch(daily_root + remote_path, destination_path.joinpath(remote_path))

        _s3_object_fetch(daily_root + "simulobs.pic.gz", destination_path, allow_missing=True)


def daily(
    daily_s3_bucket: str,
    start_date: datetime.date,
    domain_name: str,
    local_path: pathlib.Path,
    alerts_baseline_remote: pathlib.Path,
):
    """
    Sync a subset of the daily output for a single date into the working
    folder for the current execution. This will allow a subsequent daily run
    on the same day to skip expensive re-processing for data that isn't
    likely to change.
    """
    daily_root = _get_daily_archive_path(daily_s3_bucket, domain_name, start_date)

    for remote_path in [
        "wrf",
        "mcip",
    ]:
        _s3_sync_fetch(
            daily_root + remote_path, local_path.joinpath(remote_path), allow_missing=True
        )

    # fetch the alerts_baseline file for creating alerts
    _s3_object_fetch(
        _format_s3_url(daily_s3_bucket, alerts_baseline_remote), local_path
    )


def baseline(
    daily_s3_bucket: str,
    public_s3_bucket: str,
    start_date: datetime.date,
    end_date: datetime.date,
    domain_name: str,
    domain_version: str,
    local_path: pathlib.Path,
):
    """
    Sync a subset of the daily output for a range of dates into the working
    folder for the current execution. This subset of the daily data is needed
    to calculate baseline emissions for generating alerts.
    """
    fetch_domain(public_s3_bucket, domain_name, domain_version, local_path)

    for date in _date_range(start_date, end_date):  # this is inclusive of END_DATE
        destination_path = pathlib.Path(
            local_path,
            domain_name,
            "baseline",
            str(date.year),
            f"{date.month:02}",
            f"{date.day:02}",
        )

        daily_root = _get_daily_archive_path(daily_s3_bucket, domain_name, date)

        # baseline calculation requires input/test_obs.pic.gz and simulobs.pic.gz for each day
        # use exclude/include to download a single file
        _s3_sync_fetch(
            daily_root + "input",
            destination_path.joinpath("input"),
            allow_missing=True,
            extra_params=["--exclude=*", "--include=test_obs.pic.gz"],
        )
        _s3_object_fetch(daily_root + "simulobs.pic.gz", destination_path, allow_missing=True)


def fetch_domain(s3_bucket_name: str, domain_name: str, domain_version: str, output_path: pathlib.Path):
    domain_filename = f"domain.{domain_name}.nc"

    s3_url = _format_s3_url(
        s3_bucket_name=s3_bucket_name,
        s3_path=pathlib.Path('domains', domain_name, domain_version, domain_filename),
    )

    logger.debug(f"Fetching {domain_name} domain from {s3_url}")

    _s3_object_fetch(
        s3_path=s3_url,
        local_path=output_path,
    )


def _format_s3_url(s3_bucket_name: str, s3_path: str | pathlib.Path = None) -> str:
    s3_bucket = (s3_bucket_name if s3_bucket_name.startswith("s3://") else f"s3://{s3_bucket_name}").rstrip("/")
    if s3_path is None:
        return s3_bucket

    return "/".join([s3_bucket, str(s3_path)])


def _get_daily_archive_path(s3_bucket_name: str, domain_name: str, date: datetime.date) -> str:
    daily_archive_path = (
        domain_name,
        "daily",
        str(date.year),
        f"{date.month:02}",
        f"{date.day:02}",
    )

    s3_url = _format_s3_url(s3_bucket_name, '/'.join(daily_archive_path))

    return s3_url + "/"  # S3 directory paths must end with a slash


def _s3_sync_fetch(
    s3_path: str, local_path: pathlib.Path, extra_params=None, allow_missing: bool = False
):
    _s3_fetch(
        s3_path,
        local_path,
        single_file=False,
        extra_params=extra_params,
        allow_missing=allow_missing,
    )


def _s3_object_fetch(
    s3_path: str, local_path: pathlib.Path, extra_params=None, allow_missing: bool = False
):
    _s3_fetch(
        s3_path,
        local_path,
        single_file=True,
        extra_params=extra_params,
        allow_missing=allow_missing,
    )


def _s3_fetch(
    s3_path: str,
    local_path: pathlib.Path,
    single_file: bool,
    extra_params=None,
    allow_missing: bool = False,
):
    """
    Fetch an entire folder from s3 using `aws s3 sync`
    :param s3_path: Remote path starting with s3://BUCKET_NAME
    :param local_path: Local path where the files should be synced to
    :param single_file: If True, fetch a single file instead of downloading an entire folder
    :param extra_params: Additional arguments to be passed to `aws s3 sync`
    :param allow_missing: If true, missing files in the s3 bucket will be skipped
    """
    if extra_params is None:
        extra_params = []

    # Verify that the path exists
    # Raises CalledProcessError if the path doesn't exist
    try:
        subprocess.run(["aws", "s3", "ls", s3_path], check=True, capture_output=False) # noqa: S603 S607
    except subprocess.CalledProcessError:
        # if no data is available, there is no archive to restore
        if allow_missing:
            print(f"Skipping {s3_path}")
            return
        raise

    local_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading {s3_path} to {local_path}")

    # Download the path or file
    operation = "cp" if single_file else "sync"
    command = ["aws", "s3", operation, "--no-progress", *extra_params, s3_path, str(local_path)]
    try:
        res = subprocess.run(command, check=True, capture_output=True, text=True) # noqa: S603
    except subprocess.CalledProcessError as error:
        print(f"S3 fetch failed with stdout:\n{error.output}\nstderr:\n{error.stderr}")
        raise
    logger.debug(f"Output from {' '.join(res.args)}: {res.stdout}")


def _date_range(start_date: datetime.date, end_date: datetime.date):
    """Like range() but with days and inclusive of the end date."""
    for n in range((end_date - start_date).days + 1):
        yield start_date + datetime.timedelta(days=n)
