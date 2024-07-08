#!/usr/bin/env bash
# Loads the required modules on Gadi for running openmethane.
#
# This should be sourced prior to running any of the openmethane scripts.

#cmaq-stuff
module purge
module load pbs
module load intel-compiler/2019.3.199
module load openmpi/4.0.3
module load netcdf/4.7.1
module load hdf5/1.10.5
module load nco

#python-stuff
module load python3/3.11.7
[[ ":$PATH:" != *":$HOME/poetry/bin:"* ]] && export PATH="$HOME/poetry/bin:${PATH}"
source $(poetry env info --path)/bin/activate