#!/usr/bin/env bash
# Archives the results from a daily run to an S3 bucket
#
# This is intended to be run as part of the production deployment of the daily workflow
# so references environment variables that may not be available.
#
# Where the data is stored depends on whether the run was successful or not.
# If the run was successful the data is stored in the prefix `results/${DOMAIN_NAME}/daily/${YEAR}/${MONTH}/${DAY}`.
# If it was unsuccessful, the data is stored in the prefix `failed/${EXECUTION_ID}`
# with the execution ID of the workflow in AWS step functions if available,
# otherwise falling back to current isocode.
#
# This will overwrite any existing daily output with the same domain, year, month, and day.

set -Eeuo pipefail
set -x

# Helper utilities
source scripts/environment.sh


TARGET_BUCKET=${TARGET_BUCKET:-s3://test-bucket}
SUCCESS=${SUCCESS:-false}

# Write out metadata about the current run
# TODO: This could be a python script
EXECUTION_ID=${EXECUTION_ID:-$(date -u +"%Y-%m-%dT%H%M%SZ00")}
echo $EXECUTION_ID > $STORE_PATH/execution_id.txt


if [[ "$SUCCESS" == "true" ]]; then
  echo "Daily run successful"

  YEAR=$(date -u +"%Y" -d $START_DATE)
  MONTH=$(date -u +"%m" -d $START_DATE)
  DAY=$(date -u +"%d" -d $START_DATE)

  PREFIX=results/${DOMAIN_NAME}/daily/${YEAR}/${MONTH}/${DAY}
  echo "Writing data to ${TARGET_BUCKET}/${PREFIX}"

  aws s3 sync ${STORE_PATH} ${TARGET_BUCKET}/${PREFIX}
else
  echo "Run failed"
  echo "Syncing ${STORE_PATH} to S3 for later analysis"


  PREFIX=failed/${EXECUTION_ID}
  echo "Writing data to ${TARGET_BUCKET}/${PREFIX}"

  aws s3 sync ${STORE_PATH} ${TARGET_BUCKET}/failed/${EXECUTION_ID}
fi


# Clean up EFS
rm -r ${STORE_PATH}