"""Archives the results from a workflow run to an S3 bucket.

Where the data is stored depends on whether the run was successful or not.

If the run was successful the data is stored in the prefix
`${DOMAIN_NAME}/daily/${YEAR}/${MONTH}/${DAY}` or
`${DOMAIN_NAME}/monthly/${YEAR}/${MONTH}`
depending on the value of $RUN_TYPE.

If it was unsuccessful, the data is stored in the prefix
`${DOMAIN_NAME}/failed/${EXECUTION_ID}`
with the execution ID of the workflow.
"""

import json
import logging
import pathlib
import shutil
import subprocess
import sys
from datetime import datetime

# Loads environment using the value of the environment variable "TARGET"
from fourdvar.env import env

TARGET_BUCKET = env.str("TARGET_BUCKET")
DOMAIN_NAME = env.str("DOMAIN_NAME")
START_DATE: datetime.date = env.date("START_DATE")
START_DATE_RAW = env.str("START_DATE")
END_DATE = env.date("END_DATE")
RUN_TYPE = env.str("RUN_TYPE")
SUCCESS = env.bool("SUCCESS")
EXECUTION_ID = env.str("EXECUTION_ID")


def main():
    store_path = get_store_path()
    prefix = get_prefix()

    dump_run_information(store_path, prefix)

    s3_result = subprocess.run(
        ("aws", "s3", "sync", "--no-progress", str(store_path), f"{TARGET_BUCKET}/{prefix}"),  # noqa: S603
        check=False,
    )
    if s3_result.returncode == 1:
        # We only want to catch an return code of 1 as this is a substantial failure
        # s3_result.returncode could be 2 if new directories are required
        logging.error("Sync failed with exit code 1")
        sys.exit(1)

    shutil.rmtree(store_path)


def dump_run_information(store_path: pathlib.Path, prefix: str):
    logging.debug(f"""Configuration:
TARGET_BUCKET  = {TARGET_BUCKET!r}
DOMAIN_NAME    = {DOMAIN_NAME!r}
START_DATE_RAW = {START_DATE_RAW!r}
START_DATE     = {START_DATE}
END_DATE       = {END_DATE}
RUN_TYPE       = {RUN_TYPE!r}
SUCCESS        = {SUCCESS!r}
EXECUTION_ID   = {EXECUTION_ID!r}
store_path     = {store_path}
prefix         = {prefix!r}
""")

    with (store_path / "environment.txt").open("w") as fd:
        json.dump(env.dump(), fd)
    with (store_path / "execution_id.txt").open("w") as fd:
        fd.write(f"{EXECUTION_ID}\n")


def get_store_path() -> pathlib.Path:
    """Recomputing STORE_PATH works when started from step functions and eventbridge."""
    return pathlib.Path("/opt/project/data/") / DOMAIN_NAME / START_DATE_RAW / EXECUTION_ID


def get_prefix() -> str:
    if not SUCCESS:
        return f"{DOMAIN_NAME}/failed/{EXECUTION_ID}"
    if RUN_TYPE == "daily":
        return f"{DOMAIN_NAME}/daily/{START_DATE.year}/{START_DATE.month}/{START_DATE.day}"
    elif RUN_TYPE == "monthly":
        return f"{DOMAIN_NAME}/monthly/{START_DATE.year}/{START_DATE.month}"
    raise ValueError(f"Unknown RUN_TYPE={RUN_TYPE!r}")


if __name__ == "__main__":
    logging.basicConfig(level=env.str("LOG_LEVEL", "DEBUG"))
    main()
