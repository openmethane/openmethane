#!/usr/bin/env bash

SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)

OPENMETHANE_PATH=${OPENMETHANE_PATH:-"$SCRIPT_DIR/.."}
OPENMETHANE_PRIOR_PATH=${OPENMETHANE_PRIOR_PATH:-"$OPENMETHANE_PATH/../openmethane-prior"}
SETUP_WRF_PATH=${SETUP_WRF_PATH:-"$OPENMETHANE_PATH/../setup-wrf"}

# Build images
SETUP_WRF_VERSION=$(grep -Po '^version = "\K.*?(?=")' "$SETUP_WRF_PATH/pyproject.toml")
echo "Building setup-wrf v$SETUP_WRF_VERSION"
docker build "$SETUP_WRF_PATH" --build-arg SETUP_WRF_VERSION="v$SETUP_WRF_VERSION" -t "setup-wrf"

OPENMETHANE_PRIOR_VERSION=$(grep -Po '^version = "\K.*?(?=")' "$OPENMETHANE_PRIOR_PATH/pyproject.toml")
echo "Building openmethane-prior v$OPENMETHANE_PRIOR_VERSION"
docker build "$OPENMETHANE_PRIOR_PATH" --build-arg OPENMETHANE_PRIOR_VERSION="v$OPENMETHANE_PRIOR_VERSION" -t "openmethane-prior"

OPENMETHANE_VERSION=$(grep -Po '^version = "\K.*?(?=")' "$OPENMETHANE_PATH/pyproject.toml")
echo "Building openmethane v$OPENMETHANE_VERSION"
docker build "$OPENMETHANE_PATH" --build-arg OPENMETHANE_VERSION="v$OPENMETHANE_VERSION" -t "openmethane"
