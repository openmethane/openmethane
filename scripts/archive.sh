#!/usr/bin/env bash
# Archives the results from a workflow run to an S3 bucket
#
# This is intended to be run as part of the production deployment
# so references environment variables that may not be available.
#
# Where the data is stored depends on whether the run was successful or not.
# If the run was successful the data is stored in the prefix `${DOMAIN_NAME}/daily/${YEAR}/${MONTH}/${DAY}` or
# `${DOMAIN_NAME}/monthly/${YEAR}/${MONTH}` depending on the value of $RUN_TYPE.
# If it was unsuccessful, the data is stored in the prefix `${DOMAIN_NAME}/failed/${EXECUTION_ID}`
# with the execution ID of the workflow in AWS step functions if available,
# otherwise falling back to current isocode.
#
# This will overwrite any existing output with the same domain, run_type and start_date.

set -Eeuo pipefail
set -x

# Helper utilities
source scripts/environment.sh


TARGET_BUCKET=${TARGET_BUCKET:-s3://test-bucket}
SUCCESS=${SUCCESS:-false}
RUN_TYPE=${RUN_TYPE:-daily}

# Write out metadata about the current run
# TODO: This could be a python script
EXECUTION_ID=${EXECUTION_ID:-$(date -u +"%Y-%m-%dT%H%M%SZ00")}
echo $EXECUTION_ID > $STORE_PATH/execution_id.txt


if [[ "$SUCCESS" == "true" ]]; then
  echo "${RUN_TYPE} run successful"

  YEAR=$(date -u +"%Y" -d $START_DATE)
  MONTH=$(date -u +"%m" -d $START_DATE)
  DAY=$(date -u +"%d" -d $START_DATE)

  if [[ "${RUN_TYPE}" == "daily" ]]; then
    PREFIX=${DOMAIN_NAME}/daily/${YEAR}/${MONTH}/${DAY}
  elif [[ "${RUN_TYPE}" == "monthly" ]]; then
    PREFIX=${DOMAIN_NAME}/monthly/${YEAR}/${MONTH}
  else
    echo "Unknown run type: ${RUN_TYPE}"
    exit 1
  fi
else
  echo "Run failed"
  echo "Syncing ${STORE_PATH} to S3 for later analysis"

  PREFIX=${DOMAIN_NAME}/failed/${EXECUTION_ID}
fi

echo "Writing data to ${TARGET_BUCKET}/${PREFIX}"
aws s3 sync ${STORE_PATH} ${TARGET_BUCKET}/${PREFIX}

# Clean up EFS
rm -r ${STORE_PATH}