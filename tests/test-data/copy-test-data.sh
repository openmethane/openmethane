#!/usr/bin/env bash
# Copies test data from openmethane-prior and from this repository's own runs
#
# This requires that openmethane-prior, the WRF step and CMAQ preprocessing have
# been run successfully for the test-domain and 2022-12-07, with the WRF step's
# STORE_PATH set to data/ in this repository.
# This date was chosen so that there are observations over the small test domain.
# The output will be stored in `tests/test-data`
#

set -Eeuo pipefail

# The directory of the script
DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)
ROOT="$DIR/../.."

OPENMETHANE_PRIOR_ROOT="$ROOT/../openmethane-prior"
TARGET_DATE="2022-12-07"
WRF_DATE="2022120700"


# Copy the prior from openmethane-prior
cp $OPENMETHANE_PRIOR_ROOT/outputs/prior-emissions.nc $DIR/prior/

# Copy the WRF output, without its logs and namelists
rm -rf $DIR/wrf/
mkdir -p $DIR/wrf/au-test/${WRF_DATE}
cp $ROOT/data/wrf/au-test/${WRF_DATE}/WRFOUT_*.nc $DIR/wrf/au-test/${WRF_DATE}/

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