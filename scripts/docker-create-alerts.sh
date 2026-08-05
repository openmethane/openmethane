#!/usr/bin/env bash

# Create methane alerts for a single day from a completed daily run.
#
# Requires a daily run for $START_DATE (scripts/docker-e2e-daily.sh) and an
# alerts baseline for the domain (scripts/docker-alerts-baseline.sh).

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source "$SCRIPT_DIR/docker-common.sh"

# au-test is a 10x10 domain, so the default threshold of 30 yields all-NaN alerts
ALERTS_COUNT_THRESHOLD=${ALERTS_COUNT_THRESHOLD:-2}

# alerts are created from the outputs of a daily run
RUN_ID="daily/$DOMAIN_NAME/$DOMAIN_VERSION/$START_DATE"
DATA_PATH="$DATA_ROOT/$RUN_ID"
STORE_PATH="$STORE_ROOT/$RUN_ID"

DOMAIN_FILE="$STORE_PATH/domain.$DOMAIN_NAME.nc"

if [[ ! -d "$DATA_PATH" ]]; then
  cat <<EOF
No daily run found at $DATA_PATH.

Alerts are created from the outputs of a daily run. Create one with:
  START_DATE=$START_DATE bash scripts/docker-e2e-daily.sh
EOF
  exit 1
fi

if [[ ! -f "$DATA_ROOT/$ALERTS_BASELINE_NAME" ]]; then
  cat <<EOF
No alerts baseline found at $DATA_ROOT/$ALERTS_BASELINE_NAME.

A baseline is built from completed daily runs over a longer period. Create one with:
  START_DATE=<first-day> END_DATE=<last-day> bash scripts/docker-alerts-baseline.sh
EOF
  exit 1
fi

# Set up env variables to pass to docker. Written to a dedicated file so that
# the daily run's own .env isn't clobbered.
ENV_FILE="$DATA_PATH/.env.create-alerts"
write_env_file "$ENV_FILE" daily


echo "Creating alerts for $START_DATE from the daily run in $DATA_PATH"

# JobName: alerts-create-alerts
docker run --name="create-alerts" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":"$STORE_ROOT" \
  -e ALERTS_BASELINE_FILE="$STORE_ROOT/$ALERTS_BASELINE_NAME" \
  -e ALERTS_DAILY_DIR="$STORE_PATH" \
  -e ALERTS_OUTPUT_FILE="$STORE_PATH/alerts.nc" \
  -e ALERTS_COUNT_THRESHOLD="$ALERTS_COUNT_THRESHOLD" \
  "$OPENMETHANE_IMAGE" python scripts/alerts/create_alerts.py

echo "Success: alerts complete"
echo "Alerts in: $DATA_PATH/alerts.nc"
