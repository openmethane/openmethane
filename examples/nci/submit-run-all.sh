#!/usr/bin/env bash
#PBS -P q90
#PBS -N test_py4dvar
#PBS -l walltime=1:00:00,mem=10GB
#PBS -l ncpus=16
#PBS -l wd
#PBS -l jobfs=5GB

# Runs all the steps required for a full OpenMethane run on NCI.
#
# This is assumed to be submitted from the repository root:
#   qsub examples/nci/submit-run-all.sh
#
# NOTE: NCI/Gadi is no longer officially supported — see examples/nci/README.md.

source examples/nci/load_p4d_modules.sh

export TARGET=nci-nsw

bash scripts/run-all.sh
