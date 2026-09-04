#!/bin/bash
# """
# submit_fetch.sh
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
#PBS -q copyq
#PBS -N tropomi_download
#PBS -l walltime=10:00:00,mem=32GB
#PBS -l storage=gdata/sx70+gdata/hh5+gdata/ua8+gdata/ub4
#PBS -l ncpus=1
#PBS -l wd
#
# NOTE: NCI/Gadi is no longer officially supported — see examples/nci/README.md.
# Submit from the repository root:
#   qsub examples/nci/obs_preprocess/submit_fetch.sh
#
# Adjust the config file and date range below to suit your run.

source examples/nci/load_p4d_modules.sh

uv run python scripts/obs_preprocess/fetch_tropomi.py \
  --start-date 2022-07-01 \
  --end-date 2022-07-30
