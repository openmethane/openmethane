#!/bin/bash
# submit.sh
#
#
# Copyright 2023 Superpower Institute.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
#PBS -P q90
#PBS -q normal
#PBS -N obs_preproc
#PBS -l walltime=24:00:00,mem=128GB
#PBS -l ncpus=48
#PBS -l wd
#
# NOTE: NCI/Gadi is no longer officially supported — see examples/nci/README.md.
# Submit from the repository root:
#   qsub examples/nci/obs_preprocess/submit_tropomi_methane_preprocess.sh
#
# Set TROPOMI_SOURCE to a glob matching the raw TROPOMI files to preprocess.

source examples/nci/load_p4d_modules.sh

TROPOMI_SOURCE=${TROPOMI_SOURCE:-"${STORE_PATH:?STORE_PATH must be set}/tropomi/*/*.nc4"}

uv run python scripts/obs_preprocess/tropomi_methane_preprocess.py --source "${TROPOMI_SOURCE}"
