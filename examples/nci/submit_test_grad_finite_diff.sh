#!/bin/bash
# submit.sh
#
#
# Copyright 2016 University of Melbourne.
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
#PBS -q hugemem
#PBS -N test_grad
#PBS -l walltime=48:00:00,mem=999GB
#PBS -l ncpus=48
#PBS -l wd
#PBS -l jobfs=1400GB
####PBS -L storage=scratch/q90
#
# NOTE: NCI/Gadi is no longer officially supported — see examples/nci/README.md.
# Submit from the repository root:
#   qsub examples/nci/submit_test_grad_finite_diff.sh
source examples/nci/load_p4d_modules.sh
# replace previous line with whatever you source to run py4dvar

uv run python tests/integration/fourdvar/test_grad_finite_diff.py
