#!/usr/bin/env bash

SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)

OPENMETHANE_PATH=${OPENMETHANE_PATH:-"$SCRIPT_DIR/.."}
OPENMETHANE_PRIOR_PATH=${OPENMETHANE_PRIOR_PATH:-"$OPENMETHANE_PATH/../openmethane-prior"}

# Build images
OPENMETHANE_PRIOR_VERSION=$(grep -Po '^version = "\K.*?(?=")' "$OPENMETHANE_PRIOR_PATH/pyproject.toml")
echo "Building openmethane-prior v$OPENMETHANE_PRIOR_VERSION"
docker build "$OPENMETHANE_PRIOR_PATH" --build-arg OPENMETHANE_PRIOR_VERSION="v$OPENMETHANE_PRIOR_VERSION" -t "openmethane-prior"

OPENMETHANE_VERSION=$(grep -Po '^version = "\K.*?(?=")' "$OPENMETHANE_PATH/pyproject.toml")
echo "Building openmethane v$OPENMETHANE_VERSION"
docker build "$OPENMETHANE_PATH" --build-arg OPENMETHANE_VERSION="v$OPENMETHANE_VERSION" -t "openmethane"
