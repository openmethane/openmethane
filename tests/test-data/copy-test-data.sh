#!/usr/bin/env bash
# Copies test data from the openmethane-prior and WRF repositories
#
# This requires that the openmethane-prior and WRF repositories have been run successfully
# for the test-domain and 2022-07-22.
# This date was chosen so that there are observations over the small test domain.
# The output will be stored in `tests/test-data`
#

set -Eeuo pipefail

# The directory of the script
DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)
ROOT="$DIR/../.."

SETUP_WRF_ROOT="$ROOT/../setup-wrf"
OPENMETHANE_PRIOR_ROOT="$ROOT/../openmethane-prior"
TARGET_DATE="2022-07-22"
WRF_DATE="2022072200"


# Copy the prior from openmethane-prior
cp $OPENMETHANE_PRIOR_ROOT/outputs/prior-emissions.nc $DIR/prior/

# Copy the WRF data from setup-wrf
rm -rf $DIR/wrf/
mkdir -p $DIR/wrf/aust-test/${WRF_DATE}
cp -r $SETUP_WRF_ROOT/data/wrf/aust-test/${WRF_DATE} $DIR/wrf/aust-test/${WRF_DATE}

# Copy the BC/IC from cmap_preprocess
rm -rf $DIR/cmaq/
mkdir -p $DIR/cmaq
cp -r $ROOT/data/cmaq/template_* $DIR/cmaq/

# Copy the MCIP data from cmap_preprocess
rm -rf $DIR/mcip/
mkdir -p $DIR/mcip
cp -r $ROOT/data/mcip/$TARGET_DATE $DIR/mcip/$TARGET_DATE

echo "Data copied"
echo "Current directory sizes:"

du -ch $DIR