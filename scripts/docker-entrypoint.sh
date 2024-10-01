#!/bin/bash
# Entrypoint for the docker container
# Cleans up the scratch directory if it is provided and exists

set -x;

trap stop SIGTERM SIGINT SIGQUIT SIGHUP ERR EXIT

# TODO: This only handles the CMAQ scratch directory.
# This could be more generic
SCRATCH_DIR=${CHK_PATH:-}


# Clean up the scratch directory if it exists
stop() {
  echo "Stopping the container"
  if [ -d "$SCRATCH_DIR" ]; then
    echo "Cleaning up the scratch directory: $SCRATCH_DIR"
    rm -rf $SCRATCH_DIR/*
  fi
}

# Run the docker command
exec "$@ && stop() && exit 0"
