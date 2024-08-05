#!/usr/bin/env bash
# Runs the required steps to run CMAQ in the docker container
#
# This is assumed to run from the root directory
# and the required tropomi data has been downloaded into `data/tropomi`
#

set -Eeuo pipefail
set -x

source scripts/environment.sh

SKIP_CAMS_DOWNLOAD=${SKIP_CAMS_DOWNLOAD:-}

# Skip the CAMS download if the variable is set to anything other than an empty string
if [[ -z "${SKIP_CAMS_DOWNLOAD}" ]]; then
  python scripts/cmaq_preprocess/download_cams_input.py \
    -s "${START_DATE}" \
    -e "${END_DATE}" \
    "${CAMS_FILE}"
else
  echo "Skipping CAMS download"
fi

echo "Preparing CMAQ input files"
python scripts/cmaq_preprocess/setup_for_cmaq.py

echo "Preparing template files"
# These depend on CMAQ params and the value of the TARGET env variable
python scripts/cmaq_preprocess/make_emis_template.py
python scripts/cmaq_preprocess/make_template.py
python scripts/cmaq_preprocess/make_prior.py

echo "Complete"

echo "Listing directory contents"
tree "${MET_DIR}"
tree "${CTM_DIR}"