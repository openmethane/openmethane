#!/usr/bin/env bash
# Runs the required steps to run CMAQ in the docker container
#
# This is assumed to run from the root directory.
#

set -Eeuo pipefail

# Configuration environment variables
SKIP_TROPOMI_DOWNLOAD=${SKIP_TROPOMI_DOWNLOAD:-}
STORE_DIR=${STORE_DIR:-data}
TROPOMI_DIR="${STORE_DIR}/tropomi"
TROPOMI_FETCH_CONFIG_FILE=${TROPOMI_FETCH_CONFIG_FILE:-scripts/sat_data/config.austtest.json}

export TARGET=${TARGET:-docker}
export START_DATE=${START_DATE:-2022-07-22}
export END_DATE=${END_DATE:-2022-07-22}

echo "Running for target: $TARGET"

echo "Run the CMAQ preprocessing step"
bash scripts/cmaq_preprocess/run-cmaq-preprocess.sh

echo "Downloading TROPOMI data for domain"
# Skip the TROPOMI download if the variable is set to anything other than an empty string
if [[ -z "${SKIP_TROPOMI_DOWNLOAD}" ]]; then
  mkdir -p $TROPOMI_DIR

  python scripts/sat_data/fetch.py \
    -c ${TROPOMI_FETCH_CONFIG_FILE} \
    -s ${START_DATE} \
    -e ${END_DATE}T23:59:59 \
    $TROPOMI_DIR
else
  echo "Skipping TROPOMI download"
fi

echo "Preprocessing observations"
python scripts/obs_preprocess/tropomi_methane_preprocess.py \
  --source $TROPOMI_DIR/*/*.nc4

echo "Running fourdvar"
python runscript.py

echo "Complete"

tree ${STORE_DIR}/archive_Pert
