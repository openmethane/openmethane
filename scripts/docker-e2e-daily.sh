#!/usr/bin/env bash

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

OPENMETHANE_IMAGE=${OPENMETHANE_IMAGE:-"ghcr.io/openmethane/openmethane:stable"}
OPENMETHANE_PRIOR_IMAGE=${OPENMETHANE_PRIOR_IMAGE:-"ghcr.io/openmethane/openmethane-prior:stable"}
SETUP_WRF_IMAGE=${SETUP_WRF_IMAGE:-"ghcr.io/openmethane/setup-wrf:stable"}

BUILD_LOCAL_DOCKER=${BUILD_LOCAL_DOCKER:-false}
if [[ "$BUILD_LOCAL_DOCKER" == true ]]; then
  # Build docker containers using locally checked out versions, so that local
  # changes can be easily tested
  bash "$SCRIPT_DIR/docker-build-all.sh"
fi

DATA_ROOT=${DATA_ROOT:-"/tmp/openmethane-e2e"}

# Task variables
START_DATE=${START_DATE:-2022-10-29}
END_DATE=${START_DATE:-2022-10-29}
DOMAIN_NAME=${DOMAIN_NAME:-au-test}
DOMAIN_VERSION=${DOMAIN_VERSION:-v1}
NCPUS=${NCPUS:-1} # WRF will fail on au-test if run with too many cores
BOUNDARY_TRIM=${BOUNDARY_TRIM:-1} # au-test domain is 10x10 so avoid trimming all cells

RUN_ID="daily/$DOMAIN_NAME/$DOMAIN_VERSION/$START_DATE"
DATA_PATH="$DATA_ROOT/$RUN_ID"
STORE_PATH="/opt/project/data/$RUN_ID"
CHK_PATH="$STORE_PATH/scratch"

DOMAIN_FILE="$STORE_PATH/domain.$DOMAIN_NAME.nc"

TARGET_BUCKET="s3://om-dev-results"
#TARGET_BUCKET_REDUCED="s3://om-dev-output" # WARNING: THIS WILL OVERWRITE FILES IN s3
TARGET_BUCKET_REDUCED=""


if [[ -f .env ]]; then
  echo "Loading environment from .env"
  source .env
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
DOMAIN_FILE=$DOMAIN_FILE
STORE_PATH=$STORE_PATH
CHK_PATH=$CHK_PATH
NCPUS=$NCPUS
LOG_LEVEL=DEBUG
EOF


echo "Running om-daily end-to-end, data will be stored in $DATA_PATH"

# Transpose tasks from om-infra into local docker commands

# fetch the domain file from the data store
if [[ ! -f "$DATA_PATH/domain.$DOMAIN_NAME.nc" ]]; then
  curl -s -o "$DATA_PATH/domain.$DOMAIN_NAME.nc" \
    "https://openmethane.s3.amazonaws.com/domains/$DOMAIN_NAME/$DOMAIN_VERSION/domain.$DOMAIN_NAME.nc"
fi

# This only has to be done once assuming $DATA_ROOT isn't cleared
if [[ -d "$DATA_ROOT/geog/WPS_GEOG" ]]; then
  echo "WPS_GEOG is present, skipping wrf-download_geog"
else
  # JobName: wrf-download_geog
  docker run --name="wrf-download_geog" --rm \
    --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
    "$SETUP_WRF_IMAGE" bash ./scripts/download-geog.sh
fi

# JobName: wrf-run
docker run --name="e2e-daily-wrf-run" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  "$SETUP_WRF_IMAGE" bash scripts/run-wrf.sh

# JobName: prior-generate
docker run --name="e2e-daily-prior-generate" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  -e CDSAPI_KEY="$CDSAPI_KEY" \
  -e CDSAPI_URL="$CDSAPI_URL" \
  -e INVENTORY_DOMAIN_FILE="https://openmethane.s3.amazonaws.com/domains/aust10km/v1/domain.aust10km.nc" \
  -e INPUTS="$STORE_PATH/prior/inputs" \
  -e OUTPUTS="$STORE_PATH/prior/outputs" \
  -e INTERMEDIATES="$STORE_PATH/prior/intermediates" \
  -e OUTPUT_FILENAME="prior-emissions.nc" \
  "$OPENMETHANE_PRIOR_IMAGE" bash scripts/run.sh

# JobName: obs_preprocess-fetch_tropomi
docker run --name="e2e-daily-obs_preprocess-fetch_tropomi" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  "$OPENMETHANE_IMAGE" bash scripts/obs_preprocess/fetch_tropomi.sh

# JobName: cmaq_preprocess-run
docker run --name="e2e-daily-cmaq_preprocess-run" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  -e CDSAPI_KEY="$CDSAPI_KEY" \
  -e CDSAPI_URL="$CDSAPI_URL" \
  -e NUM_PROC_COLS=1 \
  -e NUM_PROC_ROWS=1 \
  -e BOUNDARY_TRIM="$BOUNDARY_TRIM" \
  "$OPENMETHANE_IMAGE" bash scripts/cmaq_preprocess/run-cmaq-preprocess.sh

# JobName: obs_preprocess-process_tropomi
docker run --name="e2e-daily-obs_preprocess-process_tropomi" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  "$OPENMETHANE_IMAGE" bash scripts/obs_preprocess/process_tropomi.sh

# JobName: fourdvar-daily
docker run --name="e2e-daily-fourdvar-daily" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  "$OPENMETHANE_IMAGE" python scripts/fourdvar/run_daily_step.py

echo "Success: daily run complete"
echo "Results in: $DATA_PATH"
echo "To create alerts for this day, run: START_DATE=$START_DATE bash scripts/docker-create-alerts.sh"
