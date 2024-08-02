#!/usr/bin/env bash
# Upload domain information to the CloudFlare bucket
#
# This is assumed to run from the root directory.
# This requires credentials for the Bucket.
#

set -Eeuo pipefail

DOMAIN_DIR="data/domains"
TARGET_DIR="s3://openmethane-prior/domains"

COMMON_S3_ARGS="--endpoint-url https://8f8a25e8db38811ac9f26a347158f296.r2.cloudflarestorage.com --profile cf-om-prior-r2"

echo "Checking if up to date"
res=$(aws s3 sync $TARGET_DIR $DOMAIN_DIR --dryrun $COMMON_S3_ARGS)

if [[ -n "$res" ]]; then
  echo $res
  echo
  echo "Local $DOMAIN_DIR is not up to date with $TARGET_DIR"
  echo "Run 'make sync-domains-from-cf'"
  exit 1
else
  echo "Local $DOMAIN_DIR is up to date with $TARGET_DIR"
fi

echo "Result from a dryrun"
res=$(aws s3 sync $DOMAIN_DIR $TARGET_DIR --dryrun $COMMON_S3_ARGS)
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
      aws s3 sync $DOMAIN_DIR $TARGET_DIR $COMMON_S3_ARGS
  else
    echo "Aborted"
    exit 1
  fi
else
    echo "No data to upload"
fi

echo "Done"
