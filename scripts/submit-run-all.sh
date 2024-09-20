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

export TARGET=nci-nsw

bash scripts/run-all.sh
