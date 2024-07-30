#!/usr/bin/env bash

function prepareEnvironment() {
  export TARGET=${TARGET:-docker}

  echo "Preparing environment for $TARGET"
  current_env=$(declare -p -x)
  source ".env.$TARGET"
  eval "$current_env"
}