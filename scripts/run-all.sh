#!/usr/bin/env bash
# Runs the required steps to run CMAQ in the docker container
#
# This is assumed to run from the root directory.
#

set -Eeuo pipefail

source scripts/environment.sh

echo "Run the CMAQ preprocessing step"
bash scripts/cmaq_preprocess/run-cmaq-preprocess.sh

echo "Downloading TROPOMI data for domain"
SKIP_TROPOMI_DOWNLOAD=${SKIP_TROPOMI_DOWNLOAD:-}
TROPOMI_DIR="${STORE_PATH}/tropomi"
TROPOMI_FETCH_CONFIG_FILE=${TROPOMI_FETCH_CONFIG_FILE:-config/obs_preprocess/config.austtest.json}

# Skip the TROPOMI download if the variable is set to anything other than an empty string
if [[ -z "${SKIP_TROPOMI_DOWNLOAD}" ]]; then
  mkdir -p $TROPOMI_DIR

  python scripts/obs_preprocess/fetch_tropomi.py \
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

echo 'bias correcting CAMS input'
python scripts/cmaq_preprocess/bias_correct_cams.py

echo "Running fourdvar"
python runscript.py

echo "Complete"

tree ${STORE_PATH}/archive_Pert
