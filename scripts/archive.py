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
"""

import json
import logging
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

def main():
    config = Config.from_environment()
    store_path = config.store_path or get_store_path(config)
    prefix = get_prefix(config)

    # config.dump(store_path=store_path, prefix=prefix)

    # If we have a full workflow ARN (which means we're running on AWS), we can fetch
    # the logs and archive them as well
    if config.workflow_execution_arn:
        log_directory = store_path / "logs"
        log_directory.mkdir(exist_ok=True)
        dump_workflow_logs(
            workflow_execution_arn=config.workflow_execution_arn, directory=log_directory
        )

    s3_result = subprocess.run(
        ("aws", "s3", "sync", "--no-progress", str(store_path), f"{config.target_bucket}/{prefix}"),
        check=False,
    )
    if s3_result.returncode == 1:
        # We only want to catch an return code of 1 as this is a substantial failure
        # s3_result.returncode could be 2 if new directories are required
        logging.error("Sync failed with exit code 1")
        sys.exit(1)

    # place the alerts baseline file in a more general location, based on config
    if config.alerts_baseline_file.exists():
        s3_result_alerts = subprocess.run(
            (
                "aws", "s3", "cp", "--no-progress",
                str(config.alerts_baseline_file),
                f"{config.target_bucket}/{config.alerts_baseline_remote}"
            ),
            check=False,
        )

    # if requested, also push a reduced set of results to a second bucket
    if config.target_bucket_reduced:
        s3_result_reduced = subprocess.run(
            ("aws",
             "s3",
             "sync",
             "--no-progress",
             "--exclude",
             "*",
             # you can add more --include flags to include more stuff in the reduced result
             "--include",
             "environment.txt",
             str(store_path),
             f"{config.target_bucket_reduced}/{prefix}"),
            check=False,
        )
        if s3_result_reduced.returncode == 1:
            # We only want to catch an return code of 1 as this is a substantial failure
            # s3_result.returncode could be 2 if new directories are required
            logging.error("Sync to reduced results target bucket failed with exit code 1")
            sys.exit(1)

    if config.success:
        logging.debug(f"Deleting {store_path}.")
        # shutil.rmtree(store_path)
    else:
        logging.debug(f"Not deleting {store_path} for failed run - clean up manually.")
    logging.debug("Finished successfully")


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
        alerts_baseline_file = env.path('ALERTS_BASELINE_FILE')
        alerts_baseline_remote = env.path("ALERTS_BASELINE_REMOTE")

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
            alerts_baseline_file=alerts_baseline_file
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


def get_prefix(config: Config) -> str:
    if config.test:
        return f"tests/{config.execution_id}"
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
    logging.info(f"Fetching logs from {log_group_name}/{log_stream_name}")
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
            logging.exception(msg)
            logfd.write(f"{msg}\n")
            return
        log_events = answer["events"]
        for le in log_events:
            timestamp = datetime.fromtimestamp(le["timestamp"] / 1000)
            logfd.write(f"{timestamp.isoformat()}: {le['message']}\n")


if __name__ == "__main__":
    logging.basicConfig(level=env.str("LOG_LEVEL", "DEBUG"))
    main()
