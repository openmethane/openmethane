#!/usr/bin/env bash

# Shared configuration and helpers for the docker-* workflow scripts.
#
# Source this from the top of a workflow script, after setting any defaults that
# differ from the ones below:
#
#   SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
#   source "$SCRIPT_DIR/docker-common.sh"
#
# Every variable is set with `:-`, so anything already present in the
# environment (or set by the calling script) takes precedence.

DOCKER_COMMON_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

OPENMETHANE_IMAGE=${OPENMETHANE_IMAGE:-"ghcr.io/openmethane/openmethane:stable"}
OPENMETHANE_PRIOR_IMAGE=${OPENMETHANE_PRIOR_IMAGE:-"ghcr.io/openmethane/openmethane-prior:stable"}
SETUP_WRF_IMAGE=${SETUP_WRF_IMAGE:-"ghcr.io/openmethane/setup-wrf:stable"}

BUILD_LOCAL_DOCKER=${BUILD_LOCAL_DOCKER:-false}
if [[ "$BUILD_LOCAL_DOCKER" == true ]]; then
  # Build docker containers using locally checked out versions, so that local
  # changes can be easily tested
  bash "$DOCKER_COMMON_DIR/docker-build-all.sh"
fi

# the location on disk where data and results will be stored
DATA_ROOT=${DATA_ROOT:-"/tmp/openmethane-e2e"}

# the location in the container where $DATA_ROOT is mounted
STORE_ROOT="/app/data"

# Task variables
START_DATE=${START_DATE:-2022-10-29}
END_DATE=${END_DATE:-$START_DATE}
DOMAIN_NAME=${DOMAIN_NAME:-au-test}
DOMAIN_VERSION=${DOMAIN_VERSION:-v1}
NCPUS=${NCPUS:-1} # WRF will fail on au-test if run with too many cores
BOUNDARY_TRIM=${BOUNDARY_TRIM:-1} # au-test domain is 10x10 so avoid trimming all cells

# The alerts baseline is shared by every daily run of a domain, so it lives at
# the root of $DATA_ROOT rather than in a dated run directory
ALERTS_BASELINE_NAME=${ALERTS_BASELINE_NAME:-"alerts-baseline.$DOMAIN_NAME-$DOMAIN_VERSION.nc"}

if [[ -f .env ]]; then
  echo "Loading environment from .env"
  source .env
fi


# Exit with an error unless every named environment variable is set
#
#   require_env CDSAPI_URL CDSAPI_KEY
require_env() {
  local missing=()

  for name in "$@"; do
    if [[ -z "${!name}" ]]; then
      missing+=("$name")
    fi
  done

  if (( ${#missing[@]} > 0 )); then
    echo "${missing[*]} env variables must be set or present in .env"
    exit 1
  fi
}

# Download the domain file for the configured domain, unless already present
#
#   fetch_domain_file "$DATA_PATH"
fetch_domain_file() {
  local data_path="$1"

  if [[ ! -f "$data_path/domain.$DOMAIN_NAME.nc" ]]; then
    curl -s -o "$data_path/domain.$DOMAIN_NAME.nc" \
      "https://openmethane.s3.amazonaws.com/domains/$DOMAIN_NAME/$DOMAIN_VERSION/domain.$DOMAIN_NAME.nc"
  fi
}

# Write the env file shared by every task in a workflow
#
#   write_env_file "$ENV_FILE" daily
#
# Expects $STORE_PATH and $DOMAIN_FILE to be set. $CHK_PATH is included when set.
write_env_file() {
  local env_file="$1"
  local run_type="$2"
  local target="docker"

  if [[ "$run_type" == "monthly" ]]; then
    target="docker-monthly"
  fi

  cat > "$env_file" <<EOF
RUN_TYPE=$run_type
TARGET=$target
START_DATE=$START_DATE
END_DATE=$END_DATE
DOMAIN_NAME=$DOMAIN_NAME
DOMAIN_VERSION=$DOMAIN_VERSION
DOMAIN_FILE=$DOMAIN_FILE
STORE_PATH=$STORE_PATH
NCPUS=$NCPUS
LOG_LEVEL=${LOG_LEVEL:-DEBUG}
EOF

  if [[ -n "$CHK_PATH" ]]; then
    echo "CHK_PATH=$CHK_PATH" >> "$env_file"
  fi
}
