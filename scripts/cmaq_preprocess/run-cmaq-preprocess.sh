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
SKIP_CMAQ_SETUP=${SKIP_CMAQ_SETUP:-}
SKIP_TEMPLATE_GENERATION=${SKIP_TEMPLATE_GENERATION:-}

# Skip the CAMS download if the variable is set to anything other than an empty string
if [[ -z "${SKIP_CAMS_DOWNLOAD}" ]]; then
  python scripts/cmaq_preprocess/download_cams_input.py \
    -s "${START_DATE}" \
    -e "${END_DATE}" \
    "${CAMS_FILE}"
else
  echo "Skipping CAMS download"
fi

if [[ -z "${SKIP_CMAQ_SETUP}" ]]; then
  echo "Preparing CMAQ input files"
  python scripts/cmaq_preprocess/setup_for_cmaq.py
else
  echo "Skipping CMAQ setup"
fi

# Skip the template generation if SKIP_TEMPLATE_GENERATION is set to anything other than an empty string
if [[ -n "${SKIP_TEMPLATE_GENERATION}" ]]; then
  echo "Skipping template generation"
  exit 0
fi

echo "Preparing template files"
# These depend on CMAQ params and the value of the TARGET env variable
# The prior also has to be run before the template generation
python scripts/cmaq_preprocess/make_emis_template.py
python scripts/cmaq_preprocess/make_template.py
python scripts/cmaq_preprocess/make_prior.py

echo "Complete"

echo "Listing directory contents"
tree "${CTM_DIR}" || echo "Cannot list ${CTM_DIR}"
tree "${MET_DIR}" || echo "Cannot list ${MET_DIR}"
