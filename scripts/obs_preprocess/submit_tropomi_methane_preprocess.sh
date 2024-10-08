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
cd ~/openmethane-beta/py4dvar/obs_preprocess
source ../load_p4d_modules.sh
# replace previous line with whatever you source to run py4dvar

#python3 restart_script.py
python3 tropomi_methane_preprocess.py --source "/home/563/pjr563/scratch/tmp/202207/S5P_RPRO_L2__CH4____202207*.nc4"
