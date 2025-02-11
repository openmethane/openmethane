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
import logging
import pathlib

# Loads environment using the value of the environment variable "TARGET"
from fourdvar.env import env
from util import archive

TARGET_BUCKET = env.str("TARGET_BUCKET", "s3://test-bucket")
DOMAIN_NAME = env.str("DOMAIN_NAME")
STORE_PATH: pathlib.Path = env.path("STORE_PATH")
START_DATE = env.date("START_DATE")
END_DATE = env.date("END_DATE")
BASELINE_LENGTH_DAYS = env.int("BASELINE_LENGTH_DAYS", 365)
ALERTS_BASELINE_REMOTE = env.path("ALERTS_BASELINE_REMOTE", "")


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
            archive.daily(
                daily_s3_bucket=TARGET_BUCKET,
                start_date=START_DATE,
                domain_name=DOMAIN_NAME,
                local_path=STORE_PATH,
                alerts_baseline_remote=ALERTS_BASELINE_REMOTE,
            )

        case "baseline":
            archive.baseline(
                daily_s3_bucket=TARGET_BUCKET,
                end_date=END_DATE,
                domain_name=DOMAIN_NAME,
                local_path=STORE_PATH,
                baseline_length_days=BASELINE_LENGTH_DAYS,
            )

        # default case catches "monthly" as well
        case _:
            archive.monthly(
                daily_s3_bucket=TARGET_BUCKET,
                start_date=START_DATE,
                end_date=END_DATE,
                domain_name=DOMAIN_NAME,
                local_path=STORE_PATH,
            )


if __name__ == "__main__":
    logging.basicConfig(level=env.str("LOG_LEVEL", "DEBUG"))
    load_from_archive()
