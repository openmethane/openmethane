"""
Load previous month's output from the archive for a monthly run.

This is intended to be run as part of the production deployment
so references environment variables that may not be available.

The data is stored in
${DOMAIN_NAME}/daily/${YEAR}/${MONTH}/${DAY}/input/test_obs.pic.gz
for each day and we need all days between the start and the end date,
including the end date.
The data is downloaded to
${STORE_PATH}/{DOMAIN_NAME}/daily/${YEAR}/${MONTH}/${DAY}/input/test_obs.pic.gz
"""

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


def main():
    for date in date_range(START_DATE, END_DATE):  # this is inclusive of END_DATE
        path = (
            DOMAIN_NAME,
            "daily",
            str(date.year),
            str(date.month),
            str(date.day),
            "input",
            "test_obs.pic.gz",
        )
        s3_path = "/".join((TARGET_BUCKET, *path))
        local_path = STORE_PATH.joinpath(*path)
        local_path.mkdir(parents=True, exist_ok=True)

        logging.debug(f"Downloading {s3_path} to {local_path}")
        subprocess.run(["aws", "s3", "sync", "--no-progress", s3_path, str(local_path)], check=True)


def date_range(start_date: datetime.date, end_date: datetime.date):
    """Like range() but with days."""
    for n in range((end_date - start_date).days + 1):
        yield start_date + datetime.timedelta(days=n)


if __name__ == "__main__":
    logging.basicConfig(level=env.str("LOG_LEVEL", "DEBUG"))
    main()
