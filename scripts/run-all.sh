#!/usr/bin/env bash
# Runs the required steps to run CMAQ in the docker container
#
# This is assumed to run from the root directory
# and the required tropomi data has been downloaded into `data/tropomi`
#

set -Eeuo pipefail

echo "Running for target: $TARGET"

make prepare-templates

python scripts/obs_preprocess/tropomi_methane_preprocess.py \
  --source 'data/tropomi/*/*.nc4'

python runscript.py