#!/usr/bin/env bash

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# a monthly run covers a period, rather than the single day docker-common assumes
END_DATE=${END_DATE:-2022-10-31}

source "$SCRIPT_DIR/docker-common.sh"

RUN_ID="monthly/$DOMAIN_NAME/$DOMAIN_VERSION/$START_DATE"
DATA_PATH="$DATA_ROOT/$RUN_ID"
STORE_PATH="$STORE_ROOT/$RUN_ID"
CHK_PATH="$STORE_PATH/scratch"

DOMAIN_FILE="$STORE_PATH/domain.$DOMAIN_NAME.nc"

TARGET_BUCKET="s3://om-dev-results"

require_env CDSAPI_URL CDSAPI_KEY

# Ensure data path exists
mkdir -p "$DATA_PATH"
mkdir -p "$DATA_PATH/scratch"

# Set up env variables to pass to docker
ENV_FILE="$DATA_PATH/.env"
write_env_file "$ENV_FILE" monthly


echo "Running om-monthly end-to-end, data will be stored in $DATA_PATH"

# Transpose tasks from om-infra into local docker commands

# fetch the domain file from the data store
fetch_domain_file "$DATA_PATH"

# Local alternative to archive-load which just copies/links the files
COPY_TIMESTAMP=$(date -d "$START_DATE")
while (( $(date -d "${COPY_TIMESTAMP}" +%s) <= $(date -d "${END_DATE}" +%s) )); do
  DAILY_PATH="$DATA_ROOT/daily/$DOMAIN_NAME/$DOMAIN_VERSION/$(date -d "$COPY_TIMESTAMP" '+%Y-%m-%d')"
  # replicate the structure in /scripts/load_from_archive.py
  COPY_DESTINATION="$DATA_PATH/$DOMAIN_NAME/daily/$(date -d "$COPY_TIMESTAMP" '+%Y/%m/%d')"

  mkdir -p "$COPY_DESTINATION"
  cp -R "$DAILY_PATH"/* "$COPY_DESTINATION"

  # increment to the next day in the range
  COPY_TIMESTAMP=$(date -d "${COPY_TIMESTAMP} +1 day")
done

# JobName: prior-generate
docker run --name="e2e-monthly-prior-generate" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":"$STORE_ROOT" \
  -e CDSAPI_KEY="$CDSAPI_KEY" \
  -e CDSAPI_URL="$CDSAPI_URL" \
  -e INVENTORY_DOMAIN_FILE="https://openmethane.s3.amazonaws.com/domains/aust10km/v1/domain.aust10km.nc" \
  -e INPUTS="$STORE_PATH/prior/inputs" \
  -e OUTPUTS="$STORE_PATH/prior/outputs" \
  -e INTERMEDIATES="$STORE_PATH/prior/intermediates" \
  -e OUTPUT_FILENAME="prior-emissions.nc" \
  "$OPENMETHANE_PRIOR_IMAGE" bash scripts/run.sh

# JobName: cmaq_preprocess-run
docker run --name="e2e-monthly-cmaq_preprocess-run" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":"$STORE_ROOT" \
  -e CDSAPI_KEY="$CDSAPI_KEY" \
  -e CDSAPI_URL="$CDSAPI_URL" \
  -e NUM_PROC_COLS=1 \
  -e NUM_PROC_ROWS=2 \
  -e BOUNDARY_TRIM="$BOUNDARY_TRIM" \
  -e SKIP_CMAQ_SETUP=true \
  "$OPENMETHANE_IMAGE" bash scripts/cmaq_preprocess/run-cmaq-preprocess.sh

# JobName: cmaq_preprocess-bias_correct
docker run --name="e2e-monthly-cmaq_preprocess-bias_correct" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":"$STORE_ROOT" \
  "$OPENMETHANE_IMAGE" python scripts/cmaq_preprocess/bias_correct_cams.py

# JobName: fourdvar-monthly
docker run --name="e2e-monthly-fourdvar-monthly" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":"$STORE_ROOT" \
  "$OPENMETHANE_IMAGE" python runscript.py

echo "To create an alerts baseline for this period, run: START_DATE=$START_DATE END_DATE=$END_DATE bash scripts/docker-alerts-baseline.sh"

echo "Success: monthly run complete"
echo "Results in: $DATA_PATH"
