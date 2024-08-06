#!/usr/bin/env bash
# Upload domain information to the CloudFlare bucket
#
# This script checks if the local domain data is up to date with the remote S3 bucket.
# If not, it prompts the user to upload the updated data to the S3 bucket.
# This requires credentials for the Bucket and is assumed to have been run from the root directory
#

set -Eeuo pipefail
set -x

source scripts/environment.sh

GEO_DIR=${GEO_DIR:-"data/domains"}
TARGET_DIR="s3://openmethane-prior/domains"

# cf-om-prior-r2 profile is the preferred name for the profile
AWS_PROFILE=${AWS_PROFILE:-cf-om-prior-r2}
if [[ -z "${AWS_PROFILE}" ]]; then
  # We must unset the AWS_PROFILE variable if we want to use IAM api keys
  # https://github.com/boto/botocore/issues/3110
  echo "Not using an AWS_PROFILE"
  unset AWS_PROFILE
fi
AWS_ENDPOINT_URL=https://8f8a25e8db38811ac9f26a347158f296.r2.cloudflarestorage.com


echo "Checking if up to date"
res=$(aws s3 sync $TARGET_DIR $GEO_DIR --dryrun)

if [[ -n "$res" ]]; then
  echo $res
  echo
  echo "Local $GEO_DIR is not up to date with $TARGET_DIR"
  echo "Run 'make sync-domains-from-cf'"
  exit 1
else
  echo "Local $GEO_DIR is up to date with $TARGET_DIR"
fi

echo "Result from a dryrun"
res=$(aws s3 sync $GEO_DIR $TARGET_DIR --dryrun)
echo $res

if [[ -n "$res" ]]; then
  echo

  if [[ -z "${FORCE:-}" ]]; then
    # Prompt for user input if FORCE is empty or not set
    read -p 'Upload (y/N): '  -n 1 -r
  else
    # Force uploading if FORCE variable has non-zero length
    echo "Forcing upload because FORCE is set"
    REPLY='y'
  fi
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
      echo "Uploading data to $TARGET_DIR"
      aws s3 sync $GEO_DIR $TARGET_DIR
  else
    echo "Aborted"
    exit 1
  fi
else
    echo "No data to upload"
fi

echo "Done"
