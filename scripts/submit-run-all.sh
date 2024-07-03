#!/usr/bin/env bash
#PBS -P q90
#PBS -N test_py4dvar
#PBS -l walltime=1:00:00,mem=10GB
#PBS -l ncpus=16
#PBS -l wd
#PBS -l jobfs=5GB

# Runs the required steps to run CMAQ in the docker container
#
# This is assumed to run from the root directory.
#

source load_p4d_modules.sh

export TARGET=nci-test
export STORE_DIR=/scratch/q90/pjr563/openmethane-test
export CMAQ_PREPROCESS_CONFIG_FILE=config/cmaq/config.nci.test.json

bash scripts/run-all.sh
