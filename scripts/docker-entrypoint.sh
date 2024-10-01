#!/bin/bash
# Entrypoint for the docker container
# Cleans up the scratch directory if it is provided and exists

# set -x;

# Trap coommon failure signals
trap fail SIGTERM SIGINT SIGQUIT SIGHUP ERR

# TODO: This only handles the CMAQ scratch directory.
# This could be more generic
SCRATCH_DIR=${CHK_PATH:-}


fail() {
  echo "Failed to run the command"
  cleanup
  exit 1
}


# Clean up the scratch directory if it exists
cleanup() {
  echo "Cleaning up the container"
  if [ -d "$SCRATCH_DIR" ]; then
    echo "Cleaning up the scratch directory: $SCRATCH_DIR"
    rm -rf $SCRATCH_DIR/*
  fi
}

# Run the docker command
"$@"

# Successfully ran the command
cleanup
exit
