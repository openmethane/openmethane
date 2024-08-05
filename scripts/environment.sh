#!/usr/bin/env bash
# Prepares the environment for the specified target
#
# This preferences preexisting environment variables over variables defined in the `.env.${TARGET}` file.
#

export TARGET=${TARGET:-docker}

echo "Preparing environment for $TARGET"
current_env=$(declare -p -x)

# Load the environment variables from the `.env.${TARGET}` file
set -a
source ".env.${TARGET}" set
set +a

eval "$current_env"

echo "Environment:"
env