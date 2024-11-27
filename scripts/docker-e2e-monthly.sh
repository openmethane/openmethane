#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Build docker containers using locally checked out versions, so that local
# changes can be easily tested
bash "$SCRIPT_DIR/docker-build-all.sh"

DATA_ROOT="/tmp/openmethane-e2e"

# Task variables
START_DATE=${START_DATE:-2022-07-22}
END_DATE=${END_DATE:-2022-07-22}
DOMAIN_NAME=${DOMAIN_NAME:-aust-test}
DOMAIN_VERSION=${DOMAIN_VERSION:-v1}
NCPUS=${NCPUS:-1} # WRF will fail on aust-test if run with too many cores
BOUNDARY_TRIM=${BOUNDARY_TRIM:-1} # aust-test domain is 10x10 so avoid trimming all cells

RUN_ID="monthly/$DOMAIN_NAME/$DOMAIN_VERSION/$START_DATE"
DATA_PATH="$DATA_ROOT/$RUN_ID"
STORE_PATH="/opt/project/data/$RUN_ID"
CHK_PATH="$STORE_PATH/scratch"

if [[ ! -f "$HOME/.cdsapirc" ]]; then
  echo "\$HOME/.cdsapirc must have a valid url and key to continue"
  exit 1
fi
CDSAPI_KEY=$(grep -Po '^key: \K.*?$' "$HOME/.cdsapirc")
CDSAPI_URL=$(grep -Po '^url: \K.*?$' "$HOME/.cdsapirc")

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
STORE_PATH=$STORE_PATH
CHK_PATH=$CHK_PATH
NCPUS=$NCPUS
EOF


echo "Running om-monthly end-to-end, data will be stored in $DATA_PATH"

# Transpose tasks from om-infra into local docker commands

# JobName: archive-load
# In AWS, we load daily results from S3 for the period spanned by the monthly
# run. Here we can just copy/link the files from the data folder.
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
  -e INPUTS="$STORE_PATH/prior/inputs" \
  -e OUTPUTS="$STORE_PATH/prior/outputs" \
  -e INTERMEDIATES="$STORE_PATH/prior/intermediates" \
  -e OUTPUT_DOMAIN="out-om-domain-info.nc" \
  "openmethane-prior" bash scripts/run.sh

# JobName: cmaq_preprocess-run
docker run --name="e2e-monthly-cmaq_preprocess-run" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":/opt/project/data \
  -e CDSAPI_KEY="$CDSAPI_KEY" \
  -e CDSAPI_URL="$CDSAPI_URL" \
  -e NUM_PROC_COLS=1 \
  -e NUM_PROC_ROWS=1 \
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


# Clean up
#rm -rf "$DATA_PATH"