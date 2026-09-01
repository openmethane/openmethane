#!/usr/bin/env bash

# Create an alerts baseline for a domain from completed daily runs.
#
# The baseline is required by scripts/docker-create-alerts.sh, and is built from
# the observations and simulated observations produced by daily runs, so run
# scripts/docker-e2e-daily.sh for each day of the desired period first.

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# a baseline is built from a period of daily runs, rather than the single day
# docker-common assumes
END_DATE=${END_DATE:-2022-10-31}

source "$SCRIPT_DIR/docker-common.sh"

RUN_ID="alerts-baseline/$DOMAIN_NAME/$DOMAIN_VERSION/$START_DATE"
DATA_PATH="$DATA_ROOT/$RUN_ID"
STORE_PATH="$STORE_ROOT/$RUN_ID"

DAILY_ROOT="$DATA_ROOT/daily/$DOMAIN_NAME/$DOMAIN_VERSION"

DOMAIN_FILE="$STORE_PATH/domain.$DOMAIN_NAME.nc"

# Ensure data path exists
mkdir -p "$DATA_PATH"

# Set up env variables to pass to docker
ENV_FILE="$DATA_PATH/.env"
write_env_file "$ENV_FILE" monthly


echo "Creating alerts baseline for $START_DATE to $END_DATE from daily runs in $DAILY_ROOT"

# Collect the daily runs in the date range into one directory of symlinks, so
# that alerts_baseline.py can pick them up with a single glob. Links are
# relative, so they resolve both on the host and under the container mount.
DAILY_LINKS="$DATA_PATH/daily"
rm -rf "$DAILY_LINKS"
mkdir -p "$DAILY_LINKS"

DAILY_FOUND=0
LINK_TIMESTAMP=$(date -d "$START_DATE")
while (( $(date -d "${LINK_TIMESTAMP}" +%s) <= $(date -d "${END_DATE}" +%s) )); do
  LINK_DATE=$(date -d "$LINK_TIMESTAMP" '+%Y-%m-%d')

  if [[ -d "$DAILY_ROOT/$LINK_DATE" ]]; then
    ln -sfnr "$DAILY_ROOT/$LINK_DATE" "$DAILY_LINKS/$LINK_DATE"
    DAILY_FOUND=$((DAILY_FOUND + 1))
  else
    echo "WARNING: no daily run at $DAILY_ROOT/$LINK_DATE, excluding $LINK_DATE from the baseline"
  fi

  # increment to the next day in the range
  LINK_TIMESTAMP=$(date -d "${LINK_TIMESTAMP} +1 day")
done

if (( DAILY_FOUND == 0 )); then
  cat <<EOF
No daily runs found in $DAILY_ROOT for $START_DATE to $END_DATE.

The baseline is built from completed daily runs. Create them with:
  START_DATE=<date> bash scripts/docker-e2e-daily.sh
EOF
  exit 1
fi

echo "Building baseline from $DAILY_FOUND daily run(s)"

# fetch the domain file from the data store
fetch_domain_file "$DATA_PATH"

# JobName: alerts-baseline
docker run --name="alerts-baseline" --rm \
  --env-file "$ENV_FILE" -v "$DATA_ROOT":"$STORE_ROOT" \
  -e ALERTS_BASELINE_DIRS="$STORE_PATH/daily/*" \
  -e ALERTS_BASELINE_FILE="$STORE_ROOT/$ALERTS_BASELINE_NAME" \
  "$OPENMETHANE_IMAGE" python scripts/alerts/alerts_baseline.py

echo "Success: alerts baseline complete"
echo "Baseline in: $DATA_ROOT/$ALERTS_BASELINE_NAME"
