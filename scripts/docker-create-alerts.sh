#!/usr/bin/env bash

# Create methane alerts for a single day from a completed daily run.
#
# Requires a daily run for $START_DATE (scripts/docker-e2e-daily.sh) and an
# alerts baseline for the domain (scripts/docker-alerts-baseline.sh).

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

OPENMETHANE_IMAGE=${OPENMETHANE_IMAGE:-"ghcr.io/openmethane/openmethane:stable"}

BUILD_LOCAL_DOCKER=${BUILD_LOCAL_DOCKER:-false}
if [[ "$BUILD_LOCAL_DOCKER" == true ]]; then
  # Build docker containers using locally checked out versions, so that local
  # changes can be easily tested
  bash "$SCRIPT_DIR/docker-build-all.sh"
fi

DATA_ROOT=${DATA_ROOT:-"/tmp/openmethane-e2e"}
# the location in the container where $DATA_ROOT is mounted
STORE_ROOT="/opt/project/data"

# Task variables
START_DATE=${START_DATE:-2022-10-29}
END_DATE=${END_DATE:-$START_DATE}
DOMAIN_NAME=${DOMAIN_NAME:-au-test}
DOMAIN_VERSION=${DOMAIN_VERSION:-v1}
# au-test is a 10x10 domain, so the default threshold of 30 yields all-NaN alerts
ALERTS_COUNT_THRESHOLD=${ALERTS_COUNT_THRESHOLD:-2}

# The baseline is shared by every daily run of a domain, so it lives at the root
# of $DATA_ROOT rather than in a dated run directory
ALERTS_BASELINE_NAME=${ALERTS_BASELINE_NAME:-"alerts-baseline.$DOMAIN_NAME-$DOMAIN_VERSION.nc"}

# alerts are created from the outputs of a daily run
RUN_ID="daily/$DOMAIN_NAME/$DOMAIN_VERSION/$START_DATE"
DATA_PATH="$DATA_ROOT/$RUN_ID"
STORE_PATH="$STORE_ROOT/$RUN_ID"

DOMAIN_FILE="$STORE_PATH/domain.$DOMAIN_NAME.nc"

if [[ -f .env ]]; then
  echo "Loading environment from .env"
  source .env
fi

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
cat > "$ENV_FILE" <<EOF
RUN_TYPE=daily
TARGET=docker
START_DATE=$START_DATE
END_DATE=$END_DATE
DOMAIN_NAME=$DOMAIN_NAME
DOMAIN_VERSION=$DOMAIN_VERSION
DOMAIN_FILE=$DOMAIN_FILE
STORE_PATH=$STORE_PATH
LOG_LEVEL=DEBUG
EOF


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
