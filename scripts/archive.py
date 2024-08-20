"""Archives the results from a workflow run to an S3 bucket.

Where the data is stored depends on whether the run was successful or not.

If the run was successful the data is stored in the prefix
`${DOMAIN_NAME}/daily/${YEAR}/${MONTH}/${DAY}` or
`${DOMAIN_NAME}/monthly/${YEAR}/${MONTH}`
depending on the value of $config.run_type.

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
from dataclasses import dataclass
from datetime import datetime

import marshmallow.utils

# Loads environment using the value of the environment variable "TARGET"
from fourdvar.env import env


def main():
    config = Config.from_environment()
    store_path = get_store_path(config)
    prefix = get_prefix(config)

    config.dump(store_path=store_path, prefix=prefix)

    s3_result = subprocess.run(
        ("aws", "s3", "sync", "--no-progress", str(store_path), f"{config.target_bucket}/{prefix}"),
        check=False,
    )
    if s3_result.returncode == 1:
        # We only want to catch an return code of 1 as this is a substantial failure
        # s3_result.returncode could be 2 if new directories are required
        logging.error("Sync failed with exit code 1")
        sys.exit(1)

    if config.success:
        logging.debug(f"Deleting {store_path}.")
        shutil.rmtree(store_path)
    else:
        logging.debug(f"Not deleting {store_path} for failed run - clean up manually.")
    logging.debug("Finished successfully")


@dataclass
class Config:
    target_bucket: str
    domain_name: str
    start_date_raw: str
    start_date: datetime.date
    end_date: datetime.date
    run_type: str
    success: bool
    execution_id: str

    @classmethod
    def from_environment(cls):
        # If called via eventbridge, we have to parse three environment variables from
        # this mushed-together environment variable
        json_input = env.str("JSON_INPUT", "")
        if json_input:
            input_dict = json.loads(json_input)
            start_date_raw = input_dict["start_date"]
            start_date = marshmallow.utils.from_iso_date(start_date_raw)
            if "end_date" in input_dict:
                end_date = marshmallow.utils.from_iso_date(input_dict["end_date"])
            else:
                end_date = start_date
            domain_name = input_dict["domain_name"]
        else:
            start_date_raw = env.str("START_DATE")
            start_date = env.date("START_DATE")
            end_date = env.date("END_DATE")
            domain_name = env.str("DOMAIN_NAME")

        target_bucket = env.str("TARGET_BUCKET")
        run_type = env.str("RUN_TYPE")
        success = env.bool("SUCCESS")
        execution_id = env.str("EXECUTION_ID")

        return cls(
            target_bucket=target_bucket,
            domain_name=domain_name,
            start_date_raw=start_date_raw,
            start_date=start_date,
            end_date=end_date,
            run_type=run_type,
            success=success,
            execution_id=execution_id,
        )

    def dump(self, store_path: pathlib.Path, prefix: str):
        logging.debug(f"""Configuration:
target_bucket  = {self.target_bucket!r}
domain_name    = {self.domain_name!r}
start_date_raw = {self.start_date_raw!r}
start_date     = {self.start_date}
end_date       = {self.end_date}
run_type       = {self.run_type!r}
success        = {self.success!r}
execution_id   = {self.execution_id!r}
store_path     = {store_path}
prefix         = {prefix!r}
""")
        with (store_path / "environment.txt").open("w") as fd:
            json.dump(env.dump(), fd)
        with (store_path / "execution_id.txt").open("w") as fd:
            fd.write(f"{self.execution_id}\n")


def get_store_path(config: Config) -> pathlib.Path:
    """Recomputing STORE_PATH works when started from step functions and eventbridge."""
    return (
        pathlib.Path("/opt/project/data/")
        / config.domain_name
        / f"{config.start_date_raw}-{config.execution_id}"
    )


def get_prefix(config: Config) -> str:
    if not config.success:
        return f"{config.domain_name}/failed/{config.execution_id}"
    if config.run_type == "daily":
        return (
            f"{config.domain_name}/daily/{config.start_date.year}/{config.start_date.month:02}/"
            f"{config.start_date.day:02}"
        )
    elif config.run_type == "monthly":
        return f"{config.domain_name}/monthly/{config.start_date.year}/{config.start_date.month:02}"
    raise ValueError(f"Unknown config.run_type={config.run_type!r}")


if __name__ == "__main__":
    logging.basicConfig(level=env.str("LOG_LEVEL", "DEBUG"))
    main()
