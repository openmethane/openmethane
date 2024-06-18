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


# Copy the prior from openmethane-prior
cp $OPENMETHANE_PRIOR_ROOT/outputs/out-om-domain-info.nc $DIR/prior/

# Copy the BC/IC from CMAQ
rm -rf $DIR/cmaq/
cp -r $SETUP_WRF_ROOT/data/cmaq/$TARGET_DATE $DIR/cmaq/

# Copy the Met data from WRF
rm -rf $DIR/mcip/
cp -r $SETUP_WRF_ROOT/data/mcip/$TARGET_DATE $DIR/mcip/

echo "Data copied"
echo "Current directory sizes:"

du -ch $DIR