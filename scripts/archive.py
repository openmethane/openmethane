"""Archives the results from a workflow run to an S3 bucket.

Where the data is stored depends on whether the run was successful or not.

If the run was successful the data is stored in the prefix
`${DOMAIN_NAME}/daily/${YEAR}/${MONTH}/${DAY}` or
`${DOMAIN_NAME}/monthly/${YEAR}/${MONTH}`
depending on the value of $config.run_type.

If it was unsuccessful, the data is stored in the prefix
`${DOMAIN_NAME}/failed/${EXECUTION_ID}`
with the execution ID of the workflow.

For manually started test runs (if successful or not), the data is stored in the prefix
`tests/${EXECUTION_ID}`
with the execution ID of the workflow.

If configured using the TARGET_BUCKET_REDUCED environment variable, a reduced set
of results to be made available publicly is also stored in the configured bucket.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import typing
from dataclasses import dataclass
from datetime import datetime

import boto3
import botocore
import marshmallow.utils

# Loads environment using the value of the environment variable "TARGET"
from fourdvar.env import env
from util.logger import get_logger

logger = get_logger(__name__)


def main():
    config = Config.from_environment()
    store_path = config.store_path or get_store_path(config)

    # config.dump(store_path=store_path, prefix=prefix)

    # If we have a full workflow ARN (which means we're running on AWS), we can fetch
    # the logs and archive them as well
    if config.workflow_execution_arn:
        log_directory = store_path / "logs"
        log_directory.mkdir(exist_ok=True)
        dump_workflow_logs(
            workflow_execution_arn=config.workflow_execution_arn, directory=log_directory
        )

    if config.test:
        archive_dir(store_path, config.target_bucket, pathlib.Path("tests", config.execution_id))
        return

    # failed executions should not archive to daily/monthly results locations
    if not config.success:
        target_path = pathlib.Path(config.domain_name, "failed", config.execution_id)
        archive_dir(store_path, config.target_bucket, target_path)
        logger.info(f"Not deleting {store_path} for failed run - clean up manually.")
        return

    if config.run_type == "daily":
        # archive the entire run to the private results bucket
        # at a path like: aust10km/daily/2023/01/01
        target_path = pathlib.Path(
            config.domain_name, "daily",
            f"{config.start_date.year:04}", f"{config.start_date.month:02}", f"{config.start_date.day:02}"
        )
        logger.debug(f"Archiving {config.run_type} run to {target_path}")
        archive_dir(store_path, config.target_bucket, target_path)

        # a small subset of results should be uploaded to the public data store
        if config.target_bucket_reduced:
            target_public_path = pathlib.Path(
                "alerts", "daily", config.domain_name,
                f"{config.start_date.year:04}", f"{config.start_date.month:02}", f"{config.start_date.day:02}"
            )
            logger.debug(f"Archiving {config.run_type} run to {target_path} in public data store.")
            archive_file(store_path / "alerts.nc", config.target_bucket_reduced, target_public_path / "alerts.nc")

    elif config.run_type == "monthly":
        # archive the entire run to the private results bucket
        # at a path like: aust10km/monthly/2023/01
        target_path = pathlib.Path(
            config.domain_name, "monthly",
            f"{config.start_date.year:04}", f"{config.start_date.month:02}"
        )
        logger.debug(f"Archiving {config.run_type} run to {target_path}")
        archive_dir(store_path, config.target_bucket, target_path)

        # on success for a monthly run, replace the alerts_baseline.nc for the domain
        # with the result from this run
        # TODO: should this check that alerts_baseline.nc is more recent than existing?
        if config.alerts_baseline_file and config.alerts_baseline_file.exists():
            logger.debug(f"Archiving {config.alerts_baseline_file} to {config.alerts_baseline_remote}")
            archive_file(config.alerts_baseline_file, config.target_bucket, config.alerts_baseline_remote)

    else:
        raise ValueError(f"Unknown config.run_type={config.run_type!r}")

    # on successful archiving, remove the folder from the store path, it's no longer needed
    logger.info(f"Deleting {store_path}.")
    shutil.rmtree(store_path)

    logger.debug("Finished successfully")


@dataclass
class Config:
    store_path: pathlib.Path
    target_bucket: str
    target_bucket_reduced: str
    domain_name: str
    start_date_raw: str
    start_date: datetime.date
    end_date: datetime.date
    run_type: str
    success: bool
    test: bool
    execution_id: str
    workflow_execution_arn: str
    alerts_baseline_file: pathlib.Path
    alerts_baseline_remote: pathlib.Path

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

        store_path = env.path("STORE_PATH")
        target_bucket = env.str("TARGET_BUCKET")
        target_bucket_reduced = env.str("TARGET_BUCKET_REDUCED", "")
        run_type = env.str("RUN_TYPE")
        success = env.bool("SUCCESS")
        test = env.bool("TEST", False)
        execution_id = env.str("EXECUTION_ID")
        workflow_execution_arn = env.str("WORKFLOW_EXECUTION_ARN", "")
        alerts_baseline_file = env.path("ALERTS_BASELINE_FILE", None)
        alerts_baseline_remote = env.path("ALERTS_BASELINE_REMOTE", None)

        return cls(
            store_path=store_path,
            target_bucket=target_bucket,
            target_bucket_reduced=target_bucket_reduced,
            domain_name=domain_name,
            start_date_raw=start_date_raw,
            start_date=start_date,
            end_date=end_date,
            run_type=run_type,
            success=success,
            execution_id=execution_id,
            test=test,
            workflow_execution_arn=workflow_execution_arn,
            alerts_baseline_remote=alerts_baseline_remote,
            alerts_baseline_file=alerts_baseline_file,
        )

    def dump(self, store_path: pathlib.Path, prefix: str):
        logger.debug(f"""Configuration:
target_bucket  = {self.target_bucket!r}
domain_name    = {self.domain_name!r}
start_date_raw = {self.start_date_raw!r}
start_date     = {self.start_date}
end_date       = {self.end_date}
run_type       = {self.run_type!r}
success        = {self.success!r}
test           = {self.test!r}
execution_id   = {self.execution_id!r}
workflow_execution_arn = {self.workflow_execution_arn!r}
alerts_baseline_remote = {self.alerts_baseline_remote!r}
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


def archive_dir(source_path: pathlib.Path, s3_bucket: str, target_path: pathlib.Path):
    s3_upload(source_path=source_path, s3_bucket=s3_bucket, target_path=target_path, single=False)


def archive_file(source_path: pathlib.Path, s3_bucket: str, target_path: pathlib.Path):
    s3_upload(source_path=source_path, s3_bucket=s3_bucket, target_path=target_path, single=True)


def s3_upload(source_path: pathlib.Path, s3_bucket: str, target_path: pathlib.Path, single: bool):
    s3_bucket_url = s3_bucket if s3_bucket.startswith("s3://") else f"s3://{s3_bucket}"
    s3_target_url = f"{s3_bucket_url}/{target_path}"

    s3_operation = "cp" if single else "sync"
    s3_result = subprocess.run(
        ("aws", "s3", s3_operation, "--no-progress", str(source_path), str(s3_target_url)),
        check=False,
    )
    if s3_result.returncode == 1:
        # We only want to catch an return code of 1 as this is a substantial failure
        # s3_result.returncode could be 2 if new directories are required
        logger.error(f"sync to {s3_bucket} failed with exit code 1")
        sys.exit(1)


def dump_workflow_logs(
    workflow_execution_arn: str,
    directory: pathlib.Path,
):
    execution_events = boto3.client(
        "stepfunctions", region_name=os.environ["AWS_REGION"]
    ).get_execution_history(executionArn=workflow_execution_arn)["events"]
    for ev in execution_events:
        if ev["type"] == "TaskStateExited":
            output = json.loads(ev["stateExitedEventDetails"]["output"])
            job_name = output["JobName"]
            for attempt_no, attempt in enumerate(output["Attempts"]):
                try:
                    log_stream_name = attempt["Container"]["LogStreamName"]
                except KeyError:
                    continue
                with (directory / f"{job_name}.{attempt_no}.log").open("w") as logfd:
                    write_stream_logfile(
                        log_group_name="/aws/batch/job",
                        log_stream_name=log_stream_name,
                        logfd=logfd,
                    )


def write_stream_logfile(log_group_name: str, log_stream_name: str, logfd: typing.TextIO):
    logger.info(f"Fetching logs from {log_group_name}/{log_stream_name}")
    logs_client = boto3.client("logs", region_name=os.environ["AWS_REGION"])
    answer = {"nextToken": None}
    while "nextToken" in answer:
        kwargs = dict(
            logGroupName=log_group_name,
            logStreamNames=[log_stream_name],
        )
        if answer["nextToken"] is not None:
            kwargs["nextToken"] = answer["nextToken"]
        try:
            answer = logs_client.filter_log_events(**kwargs)
        except botocore.exceptions.ClientError as e:
            msg = f"Error fetching logs: {e}"
            logger.exception(msg)
            logfd.write(f"{msg}\n")
            return
        log_events = answer["events"]
        for le in log_events:
            timestamp = datetime.fromtimestamp(le["timestamp"] / 1000)
            logfd.write(f"{timestamp.isoformat()}: {le['message']}\n")


if __name__ == "__main__":
    main()
