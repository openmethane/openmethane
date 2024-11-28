#!/usr/bin/env bash

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Build docker containers using locally checked out versions, so that local
# changes can be easily tested
bash "$SCRIPT_DIR/docker-build-all.sh"

DATA_ROOT=${DATA_ROOT:-"/tmp/openmethane-e2e"}

# Task variables
START_DATE=${START_DATE:-2022-07-22}
END_DATE=${START_DATE:-2022-07-22}
DOMAIN_NAME=${DOMAIN_NAME:-aust-test}
DOMAIN_VERSION=${DOMAIN_VERSION:-v1}
NCPUS=${NCPUS:-1} # WRF will fail on aust-test if run with too many cores
BOUNDARY_TRIM=${BOUNDARY_TRIM:-1} # aust-test domain is 10x10 so avoid trimming all cells

RUN_ID="daily/$DOMAIN_NAME/$DOMAIN_VERSION/$START_DATE"
DATA_PATH="$DATA_ROOT/$RUN_ID"
STORE_PATH="/opt/project/data/$RUN_ID"
CHK_PATH="$STORE_PATH/scratch"

if [[ -f .env ]]; then
  echo "Loading environment from .env"
  source .env
fi

if [ -z "$EARTHDATA_USERNAME" ] || [ -z "$EARTHDATA_PASSWORD" ]; then
  echo "EARTHDATA_USERNAME and EARTHDATA_PASSWORD env variables must be set or present in .env"
  exit 1
fi
if [ -z "$CDSAPI_URL" ] || [ -z "$CDSAPI_KEY" ]; then
  echo "CDSAPI_URL and CDSAPI_KEY env variables must be set or present in .env"
  exit 1
fi

# Ensure data path exists
mkdir -p "$DATA_PATH"
mkdir -p "$DATA_PATH/scratch"


# Set up env variables to pass to docker
ENV_FILE="$DATA_PATH/.env"
cat > "$ENV_FILE" <<EOF
RUN_TYPE=daily
TARGET=docker
START_DATE=$START_DATE
END_DATE=$END_DATE
DOMAIN_NAME=$DOMAIN_NAME
DOMAIN_VERSION=$DOMAIN_VERSION
STORE_PATH=$STORE_PATH
CHK_PATH=$CHK_PATH
NCPUS=$NCPUS
EOF


echo "Running om-daily end-to-end, data will be stored in $DATA_PATH"

# Transpose tasks from om-infra into local docker commands

# This only has to be done once assuming $DATA_ROOT isn't cleared
if [[ -d "$DATA_ROOT/geog/WPS_GEOG" ]]; then
  echo "WPS_GEOG is present, skipping wrf-download_geog"
else
  # JobName: wrf-download_geog
  docker run --name="wrf-download_geog" --rm \
    --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
    "setup-wrf" bash ./scripts/download-geog.sh
fi

# JobName: wrf-run
docker run --name="e2e-daily-wrf-run" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  "setup-wrf" bash scripts/run-wrf.sh

# JobName: prior-generate
docker run --name="e2e-daily-prior-generate" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  -e CDSAPI_KEY="$CDSAPI_KEY" \
  -e CDSAPI_URL="$CDSAPI_URL" \
  -e INPUTS="$STORE_PATH/prior/inputs" \
  -e OUTPUTS="$STORE_PATH/prior/outputs" \
  -e INTERMEDIATES="$STORE_PATH/prior/intermediates" \
  -e OUTPUT_DOMAIN="out-om-domain-info.nc" \
  "openmethane-prior" bash scripts/run.sh

# JobName: obs_preprocess-fetch_tropomi
docker run --name="e2e-daily-obs_preprocess-fetch_tropomi" --rm \
  -e EARTHDATA_USERNAME="$EARTHDATA_USERNAME" \
  -e EARTHDATA_PASSWORD="$EARTHDATA_PASSWORD" \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  openmethane bash scripts/obs_preprocess/fetch_tropomi.sh

# JobName: cmaq_preprocess-run
docker run --name="e2e-daily-cmaq_preprocess-run" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  -e CDSAPI_KEY="$CDSAPI_KEY" \
  -e CDSAPI_URL="$CDSAPI_URL" \
  -e NUM_PROC_COLS=1 \
  -e NUM_PROC_ROWS=1 \
  -e BOUNDARY_TRIM="$BOUNDARY_TRIM" \
  openmethane bash scripts/cmaq_preprocess/run-cmaq-preprocess.sh

# JobName: obs_preprocess-process_tropomi
docker run --name="e2e-daily-obs_preprocess-process_tropomi" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  openmethane bash scripts/obs_preprocess/process_tropomi.sh

# JobName: cmaq_preprocess-bias_correct
docker run --name="e2e-daily-cmaq_preprocess-bias_correct" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  openmethane python scripts/cmaq_preprocess/bias_correct_cams.py

# JobName: fourdvar-daily
docker run --name="e2e-daily-fourdvar-daily" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  openmethane python scripts/fourdvar/run_daily_step.py


# Clean up
#rm -rf "$DATA_PATH"