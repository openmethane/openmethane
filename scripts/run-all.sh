#!/usr/bin/env bash
# Runs the required steps to run CMAQ in the docker container
#
# This is assumed to run from the root directory
# and the required tropomi data has been downloaded into `data/tropomi`
#

set -Eeuo pipefail

echo "Running for target: $TARGET"

echo "Run the CMAQ preprocessing step"
bash scripts/cmaq_preprocess/run-cmaq-preprocess.sh

TROPOMI_DIR='data/tropomi'

tropomi_files=$(find $TROPOMI_DIR -type f | wc -l)
if [[ $tropomi_files -eq 0 ]]; then
  echo "No TROPOMI files found in $TROPOMI_DIR. Downloading"

  python scripts/sat_data/fetch.py \
    -c scripts/sat_data/config.austtest.json \
    -s 2022-07-22 \
    -e 2022-07-22 \
    $TROPOMI_DIR
fi

echo "Preprocessing observations"
python scripts/obs_preprocess/tropomi_methane_preprocess.py \
  --source $TROPOMI_DIR/*/*.nc4

echo "Running fourdvar"
python runscript.py

echo "Complete"

tree data/archive_Pert
