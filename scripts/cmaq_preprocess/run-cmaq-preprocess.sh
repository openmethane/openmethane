#!/usr/bin/env bash
# Runs the required steps to run CMAQ in the docker container
#
# This is assumed to run from the root directory
# and the required tropomi data has been downloaded into `data/tropomi`
#

set -Eeuo pipefail

# Configuration
TARGET=${TARGET:-docker}
CONFIG_FILE=${CMAQ_PREPROCESS_CONFIG_FILE:-config/cmaq_preprocess/config.docker.json}

echo "Running for target: $TARGET using config file: $CONFIG_FILE"

START_DATE=2022-07-22

if [[ -z "${SKIP_CAMS_DOWNLOAD}" ]]; then
  python scripts/cmaq_preprocess/download_cams_input.py \
    -s ${START_DATE} \
    -e ${START_DATE} \
    data/cams/cams_eac4_methane.nc
else
  echo "Skipping CAMS download"
fi

echo "Preparing CMAQ input files"
python scripts/cmaq_preprocess/setup_for_cmaq.py -c $CONFIG_FILE

echo "Preparing template files"
# These depend on CMAQ params and the value of the TARGET env variable
python scripts/cmaq_preprocess/make_emis_template.py
python scripts/cmaq_preprocess/make_template.py
python scripts/cmaq_preprocess/make_prior.py

echo "Complete"

tree data/cmaq
tree data/mcip