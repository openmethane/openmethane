"""
Upload domain information to the CloudFlare bucket

This script checks if the local domain data is up to date with the remote S3 bucket.
If not, it prompts the user to upload the updated data to the S3 bucket.
This requires credentials for the Bucket and is assumed to have been run from the root
directory.
"""

import logging
import os
import shlex
import subprocess
import sys

GEO_DIR = os.environ.get("GEO_DIR", "data/domains")
TARGET_DIR = "s3://openmethane-prior/domains"
# Setup AWS credentials
# You may need to set AWS_PROFILE if multiple AWS profiles are used, the common profile
# name for this application is "cf-om-prior-r2" profile.
# Otherwise API keys are required to be set outside of this script (AWS_ACCESS_KEY_ID,
# AWS_SECRET_ACCESS_KEY)
AWS_ENDPOINT_URL = "https://8f8a25e8db38811ac9f26a347158f296.r2.cloudflarestorage.com"
AWS_REGION = "apac"
EXTRA_R2_ARGS = os.environ.get("EXTRA_R2_ARGS", "")
FORCE = os.environ.get("FORCE", "")


def main():
    r2_arguments = ["--endpoint-url", AWS_ENDPOINT_URL, "--region", AWS_REGION]
    if EXTRA_R2_ARGS:
        r2_arguments += shlex.split(EXTRA_R2_ARGS)

    aws_config = subprocess.run(
        ["aws", "configure", "list"], check=True, capture_output=True, text=True
    )
    logging.debug(f"AWS configuration:\n{aws_config.stdout}")

    check_geo_dir_up_to_date(r2_arguments)

    dry_sync_output = dry_sync(r2_arguments)

    if dry_sync_output:
        if ask_upload():
            logging.info(f"Uploading data to {TARGET_DIR=}")
            subprocess.run(
                ["aws", "s3", "sync", GEO_DIR, TARGET_DIR] + r2_arguments, check=True, text=True
            )
            logging.info("Done.")
    else:
        logging.info("Nothing to upload")


def ask_upload():
    if FORCE:
        upload = True
        logging.debug(f"Forcing upload because {FORCE=}.")
    else:
        answer = input("Upload? (y/N): ")
        upload = answer.strip() in "yY"
    return upload


def dry_sync(r2_arguments):
    dry_sync_to_r2 = subprocess.run(
        ["aws", "s3", "sync", GEO_DIR, TARGET_DIR, "--dryrun"] + r2_arguments,
        check=False,
        capture_output=True,
    )
    logging.debug(
        f"""Result from a dryrun:
Stdout:
{dry_sync_to_r2.stdout}
Stderr:
{dry_sync_to_r2.stderr}"""
    )
    dry_sync_output = dry_sync_to_r2.stdout.strip()
    return dry_sync_output


def check_geo_dir_up_to_date(r2_arguments):
    logging.info("Checking if up to date")
    dry_sync_from_r2 = subprocess.run(
        ["aws", "s3", "sync", TARGET_DIR, GEO_DIR, "--dryrun"] + r2_arguments,
        check=False,
        capture_output=True,
    )
    if dry_sync_from_r2.stdout.strip():
        # the dry run did changes
        logging.debug(f"Dry run syncing from r2 to GEO_DIR reports: {dry_sync_from_r2.stdout}")
        logging.warning(f"Local {GEO_DIR=} is not up to date with {TARGET_DIR=}.")
        logging.warning("Run `make sync-domains-from-cf`")
        if not FORCE:
            sys.exit(1)
    else:
        logging.debug(f"Local {GEO_DIR=} is up to date with {TARGET_DIR=}.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
