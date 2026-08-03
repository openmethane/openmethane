#!/usr/bin/env bash
# Loads the required modules on Gadi for running openmethane.
#
# This should be sourced prior to running any of the openmethane scripts,
# from the repository root (e.g. `. examples/nci/load_p4d_modules.sh`).
#
# NOTE: NCI/Gadi is no longer officially supported by this project.
# This script is provided as-is and may no longer work — see examples/nci/README.md.
#
# Requires `uv` to already be installed and on PATH.
# See examples/nci/README.md for installation instructions.

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
if ! command -v uv >/dev/null; then
  echo "uv is required but was not found on PATH. See examples/nci/README.md for installation instructions." >&2
  return 1
fi

uv sync

# Put the project virtual environment on PATH so that the shared scripts under
# scripts/ (which invoke `python` directly) resolve to the project interpreter.
# This mirrors how the docker image exposes its virtual environment.
export PATH="${PWD}/.venv/bin:${PATH}"