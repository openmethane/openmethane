#!/usr/bin/env bash

source scripts/environment.sh

set -x

python scripts/cmaq_preprocess/upload-domains.py
