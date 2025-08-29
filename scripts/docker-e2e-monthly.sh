#!/usr/bin/env bash

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Build docker containers using locally checked out versions, so that local
# changes can be easily tested
bash "$SCRIPT_DIR/docker-build-all.sh"

DATA_ROOT=${DATA_ROOT:-"/tmp/openmethane-e2e"}

# Task variables
START_DATE=${START_DATE:-2022-10-29}
END_DATE=${END_DATE:-2022-10-31}
DOMAIN_NAME=${DOMAIN_NAME:-au-test}
DOMAIN_VERSION=${DOMAIN_VERSION:-v1}
INVENTORY_NAME=${INVENTORY_NAME:-aust10km}
INVENTORY_VERSION=${INVENTORY_VERSION:-v1}
NCPUS=${NCPUS:-1} # WRF will fail on au-test if run with too many cores
BOUNDARY_TRIM=${BOUNDARY_TRIM:-1} # au-test domain is 10x10 so avoid trimming all cells

RUN_ID="monthly/$DOMAIN_NAME/$DOMAIN_VERSION/$START_DATE"
DATA_PATH="$DATA_ROOT/$RUN_ID"
STORE_PATH="/opt/project/data/$RUN_ID"
CHK_PATH="$STORE_PATH/scratch"

DOMAIN_FILE="$STORE_PATH/domain.$DOMAIN_NAME.nc"

TARGET_BUCKET="s3://om-dev-results"

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
RUN_TYPE=monthly
TARGET=docker-monthly
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


echo "Running om-monthly end-to-end, data will be stored in $DATA_PATH"

# Transpose tasks from om-infra into local docker commands

# JobName: archive-load
# Note: this needs AWS credentials, so the script must be run using aws-vault
#docker run --name="e2e-monthly-archive-load" --rm \
#  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
#  -e TARGET_BUCKET="$TARGET_BUCKET" \
#  -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
#  -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
#  -e AWS_SESSION_TOKEN="$AWS_SESSION_TOKEN" \
#  -e AWS_REGION="$AWS_REGION" \
#  openmethane python scripts/load_from_archive.py --sync monthly

# fetch the domain file from the data store
if [[ ! -f "$DATA_PATH/domain.$DOMAIN_NAME.nc" ]]; then
  curl -s -o "$DATA_PATH/domain.$DOMAIN_NAME.nc" \
    "https://openmethane.s3.amazonaws.com/domains/$DOMAIN_NAME/$DOMAIN_VERSION/domain.$DOMAIN_NAME.nc"
fi

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
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  -e CDSAPI_KEY="$CDSAPI_KEY" \
  -e CDSAPI_URL="$CDSAPI_URL" \
  -e INVENTORY_NAME="$INVENTORY_NAME" \
  -e INVENTORY_VERSION="$INVENTORY_VERSION" \
  -e INPUTS="$STORE_PATH/prior/inputs" \
  -e OUTPUTS="$STORE_PATH/prior/outputs" \
  -e INTERMEDIATES="$STORE_PATH/prior/intermediates" \
  -e OUTPUT_FILENAME="prior-emissions.nc" \
  "openmethane-prior" bash scripts/run.sh

# JobName: cmaq_preprocess-run
docker run --name="e2e-monthly-cmaq_preprocess-run" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  -e CDSAPI_KEY="$CDSAPI_KEY" \
  -e CDSAPI_URL="$CDSAPI_URL" \
  -e NUM_PROC_COLS=1 \
  -e NUM_PROC_ROWS=2 \
  -e BOUNDARY_TRIM="$BOUNDARY_TRIM" \
  -e SKIP_CMAQ_SETUP=true \
  openmethane bash scripts/cmaq_preprocess/run-cmaq-preprocess.sh

# JobName: cmaq_preprocess-bias_correct
docker run --name="e2e-monthly-cmaq_preprocess-bias_correct" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  openmethane python scripts/cmaq_preprocess/bias_correct_cams.py

# JobName: fourdvar-monthly
docker run --name="e2e-monthly-fourdvar-monthly" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  openmethane python runscript.py

# JobName: archive-baseline-load
# Note: this needs AWS credentials, so the script must be run using aws-vault
#docker run --name="e2e-monthly-archive-baseline-load" --rm \
#  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
#  -e TARGET_BUCKET="$TARGET_BUCKET" \
#  -e BASELINE_LENGTH_DAYS="3" \
#  -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
#  -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
#  -e AWS_SESSION_TOKEN="$AWS_SESSION_TOKEN" \
#  -e AWS_REGION="$AWS_REGION" \
#  openmethane python scripts/load_from_archive.py --sync baseline

# JobName: alerts-baseline
docker run --name="e2e-monthly-alerts-baseline" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  -e ALERTS_DOMAIN_FILE="$STORE_PATH/prior/outputs/prior-emissions.nc" \
  -e ALERTS_BASELINE_DIRS="$STORE_PATH/$DOMAIN_NAME/daily/*/*/*" \
  -e ALERTS_BASELINE_FILE="$STORE_PATH/alerts-baseline.nc" \
  openmethane python scripts/alerts/alerts_baseline.py

# JobName: archive-success
# Warning: this will delete the results folder on success!
#docker run --name="e2e-monthly-archive-success" --rm \
#  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
#  -e SUCCESS="true" \
#  -e RUN_TYPE="monthly" \
#  -e EXECUTION_ID="e2e-monthly" \
#  -e TARGET_BUCKET="$TARGET_BUCKET" \
#  -e TARGET_BUCKET_REDUCED="" \
#  -e ALERTS_BASELINE_FILE="$STORE_PATH/alerts-baseline.nc" \
#  -e ALERTS_BASELINE_REMOTE="$DOMAIN_NAME/alerts-baseline.nc" \
#  -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
#  -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
#  -e AWS_SESSION_TOKEN="$AWS_SESSION_TOKEN" \
#  -e AWS_REGION="$AWS_REGION" \
#  openmethane python scripts/archive.py

echo "Success: monthly run complete"
echo "Results in: $DATA_PATH"
