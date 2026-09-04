#!/usr/bin/env bash

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source "$SCRIPT_DIR/docker-common.sh"

RUN_ID="daily/$DOMAIN_NAME/$DOMAIN_VERSION/$START_DATE"
DATA_PATH="$DATA_ROOT/$RUN_ID"
STORE_PATH="$STORE_ROOT/$RUN_ID"
CHK_PATH="$STORE_PATH/scratch"

DOMAIN_FILE="$STORE_PATH/domain.$DOMAIN_NAME.nc"

TARGET_BUCKET="s3://om-dev-results"
#TARGET_BUCKET_REDUCED="s3://om-dev-output" # WARNING: THIS WILL OVERWRITE FILES IN s3
TARGET_BUCKET_REDUCED=""

require_env CDSAPI_URL CDSAPI_KEY

# Ensure data path exists
mkdir -p "$DATA_PATH"
mkdir -p "$DATA_PATH/scratch"

# Set up env variables to pass to docker
ENV_FILE="$DATA_PATH/.env"
write_env_file "$ENV_FILE" daily


echo "Running om-daily end-to-end, data will be stored in $DATA_PATH"

# Transpose tasks from om-infra into local docker commands

# fetch the domain file from the data store
fetch_domain_file "$DATA_PATH"

# This only has to be done once assuming $DATA_ROOT isn't cleared
if [[ -d "$DATA_ROOT/geog/WPS_GEOG" ]]; then
  echo "WPS_GEOG is present, skipping wrf-download_geog"
else
  # JobName: wrf-download_geog
  docker run --name="wrf-download_geog" --rm \
    --env-file "$ENV_FILE" -v "$DATA_ROOT":"$STORE_ROOT" \
    "$SETUP_WRF_IMAGE" bash ./scripts/download-geog.sh
fi

# JobName: wrf-run
docker run --name="e2e-daily-wrf-run" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":"$STORE_ROOT" \
  "$SETUP_WRF_IMAGE" bash scripts/run-wrf.sh

# JobName: prior-generate
docker run --name="e2e-daily-prior-generate" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":"$STORE_ROOT" \
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
  --env-file "$ENV_FILE" -v "$DATA_ROOT":"$STORE_ROOT" \
  -e CDSE_USERNAME="$CDSE_USERNAME" \
  -e CDSE_PASSWORD="$CDSE_PASSWORD" \
  "$OPENMETHANE_IMAGE" bash scripts/obs_preprocess/fetch_tropomi.sh

# JobName: cmaq_preprocess-run
docker run --name="e2e-daily-cmaq_preprocess-run" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":"$STORE_ROOT" \
  -e CDSAPI_KEY="$CDSAPI_KEY" \
  -e CDSAPI_URL="$CDSAPI_URL" \
  -e NUM_PROC_COLS=1 \
  -e NUM_PROC_ROWS=1 \
  -e BOUNDARY_TRIM="$BOUNDARY_TRIM" \
  "$OPENMETHANE_IMAGE" bash scripts/cmaq_preprocess/run-cmaq-preprocess.sh

# JobName: obs_preprocess-process_tropomi
docker run --name="e2e-daily-obs_preprocess-process_tropomi" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":"$STORE_ROOT" \
  "$OPENMETHANE_IMAGE" bash scripts/obs_preprocess/process_tropomi.sh

# JobName: fourdvar-daily
docker run --name="e2e-daily-fourdvar-daily" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":"$STORE_ROOT" \
  "$OPENMETHANE_IMAGE" python scripts/fourdvar/run_daily_step.py

echo "Success: daily run complete"
echo "Results in: $DATA_PATH"
echo "To create alerts for this day, run: START_DATE=$START_DATE bash scripts/docker-create-alerts.sh"
