"""
Load previous daily output from the archive for a monthly run or a daily
re-processing.

This is intended to be run as part of the production deployment
so references environment variables that may not be available.

This script downloads archived output from a daily run
for each day between the start and end date (inclusive).

The archived data is stored in the prefix ${DOMAIN_NAME}/daily/${YEAR}/${MONTH}/${DAY}.
The script downloads specific directories from that archive,
into ${STORE_PATH}/${DOMAIN_NAME}/daily/${YEAR}/${MONTH}/${DAY}.
"""
import click
import datetime
import logging
import pathlib
import subprocess

# Loads environment using the value of the environment variable "TARGET"
from fourdvar.env import env

TARGET_BUCKET = env.str("TARGET_BUCKET", "s3://test-bucket")
DOMAIN_NAME = env.str("DOMAIN_NAME")
STORE_PATH: pathlib.Path = env.path("STORE_PATH")
START_DATE = env.date("START_DATE")
END_DATE = env.date("END_DATE")
BASELINE_LENGTH_DAYS = env.int("BASELINE_LENGTH_DAYS", 365)


@click.command()
@click.option(
    "--sync", "-s",
    help="Sync a single day ('daily') or multiple dates for a 'monthly' or 'baseline' task",
    default="monthly",
    show_default=True,
    type=click.Choice(['monthly', 'daily', 'baseline'])
)
def load_from_archive(sync: str = "monthly"):
    match sync:
        case "daily":
            daily()

        case "baseline":
            baseline()

        # default case catches "monthly" as well
        case _:
            monthly()

def monthly():
    """
    Sync a subset of the daily output for a range of dates into the working
    folder for the current execution. This daily data is needed for the monthly
    workflow.
    """
    for date in date_range(START_DATE, END_DATE):  # this is inclusive of END_DATE
        daily_destination_path = pathlib.Path(
            DOMAIN_NAME,
            "daily",
            str(date.year),
            f"{date.month:02}",
            f"{date.day:02}",
        )

        for path in [
            ["input"],
            ["cmaq"],
            ["mcip"],
        ]:
            _sync_daily_directory(date, path, daily_destination_path)


def daily():
    """
    Sync a subset of the daily output for a single date into the working
    folder for the current execution. This will allow a subsequent daily run
    on the same day to skip expensive re-processing for data that isn't
    likely to change.
    """
    for path in [
        ["wrf"],
        ["mcip"],
    ]:
        _sync_daily_directory(START_DATE, path, pathlib.Path('.'), allow_missing=True)


def baseline():
    """
    Sync a subset of the daily output for a range of dates into the working
    folder for the current execution. This subset of the daily data is needed
    to calculate baseline emissions for generating alerts.
    """
    # Aim for 12 months of data, but if requested dates don't exist in s3
    # (because a daily workflow has not yet been run) they will be skipped,
    # and the baseline will use whatever data is available.
    baseline_start = END_DATE - datetime.timedelta(days=BASELINE_LENGTH_DAYS - 1)

    for date in date_range(baseline_start, END_DATE):  # this is inclusive of END_DATE
        daily_destination_path = pathlib.Path(
            DOMAIN_NAME,
            "baseline",
            str(date.year),
            f"{date.month:02}",
            f"{date.day:02}",
        )

        # baseline calculation requires input/test_obs.pic.gz and simulobs.pic.gz for each day
        # use exclude/include to download a single file
        _sync_daily_directory(date, ["input"], daily_destination_path, allow_missing=True, extra_params=["--exclude=*", "--include=test_obs.pic.gz"])
        _sync_daily_directory(date, [], daily_destination_path, allow_missing=True, extra_params=["--exclude=*", "--include=simulobs.pic.gz"])


def _sync_daily_directory(date: datetime.date, path: list[str], destination: pathlib.Path, extra_params=None, allow_missing: bool = False):
    """
    Sync output from an archive of a successful daily workflow.

    Parameters
    ----------
    date
        Date to sync
    path
        Relative path to a directory within the daily results to fetch.

        This doesn't currently fetch individual files,
        instead an entire directory including its subdirectories are fetched.
    """
    daily_archive_path = (
        DOMAIN_NAME,
        "daily",
        str(date.year),
        f"{date.month:02}",
        f"{date.day:02}",
    )
    s3_path = "/".join((TARGET_BUCKET, *daily_archive_path, *path)).rstrip("/")
    s3_path = s3_path + "/"  # S3 directory paths must end with a slash

    local_path = STORE_PATH.joinpath(destination, *path)

    _s3_sync_fetch(s3_path, local_path, extra_params=extra_params, allow_missing=allow_missing)


def _s3_sync_fetch(s3_path: str, local_path: pathlib.Path, extra_params=None, allow_missing: bool = False):
    """
    Fetch an entire folder from s3 using `aws s3 sync`
    :param s3_path: Remote path starting with s3://BUCKET_NAME
    :param local_path: Local path where the files should be synced to
    :param allow_missing: If true, missing files in the s3 bucket will be skipped
    """
    if extra_params is None:
        extra_params = []

    # Verify that the path exists
    # Raises CalledProcessError if the path doesn't exist
    try:
        subprocess.run(["aws", "s3", "ls", s3_path], check=True, capture_output=False)
    except subprocess.CalledProcessError as error:
        # if no data is available, there is no archive to restore
        if allow_missing:
            print(f"Skipping {s3_path}")
            return
        raise error

    local_path.mkdir(parents=True, exist_ok=True)
    logging.info(f"Downloading {s3_path} to {local_path}")

    # Download the path
    command = ["aws", "s3", "sync", "--no-progress", *extra_params, s3_path, str(local_path)]
    res = subprocess.run(command, check=True, capture_output=True, text=True)
    logging.debug(f"Output from {' '.join(res.args)}: {res.stdout}")


def date_range(start_date: datetime.date, end_date: datetime.date):
    """Like range() but with days and inclusive of the end date."""
    for n in range((end_date - start_date).days + 1):
        yield start_date + datetime.timedelta(days=n)


if __name__ == "__main__":
    logging.basicConfig(level=env.str("LOG_LEVEL", "DEBUG"))
    load_from_archive()
