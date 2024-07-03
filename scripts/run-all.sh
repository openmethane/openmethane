#!/usr/bin/env bash
# Runs the required steps to run CMAQ in the docker container
#
# This is assumed to run from the root directory.
#

set -Eeuo pipefail

# Configuration environment variables
SKIP_TROPOMI_DOWNLOAD=${SKIP_TROPOMI_DOWNLOAD:-}
TROPOMI_DIR='data/tropomi'
TARGET=${TARGET:-docker}

echo "Running for target: $TARGET"

echo "Run the CMAQ preprocessing step"
bash scripts/cmaq_preprocess/run-cmaq-preprocess.sh

echo "Downloading TROPOMI data for domain"
# Skip the TROPOMI download if the variable is set to anything other than an empty string
if [[ -z "${SKIP_TROPOMI_DOWNLOAD}" ]]; then
  mkdir -p $TROPOMI_DIR

  python scripts/sat_data/fetch.py \
    -c scripts/sat_data/config.austtest.json \
    -s 2022-07-22 \
    -e 2022-07-22 \
    $TROPOMI_DIR.nc
else
  echo "Skipping TROPOMI download"
fi

echo "Preprocessing observations"
python scripts/obs_preprocess/tropomi_methane_preprocess.py \
  --source $TROPOMI_DIR/*/*.nc4

echo "Running fourdvar"
python runscript.py

echo "Complete"

tree data/archive_Pert
