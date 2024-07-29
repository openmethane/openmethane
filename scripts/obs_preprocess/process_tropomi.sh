#!/bin/bash
# """
# process_tropomi.sh
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

export TARGET=${TARGET:-docker}
export START_DATE=${START_DATE:-2022-07-22}


python scripts/obs_preprocess/tropomi_methane_preprocess.py \
      --source "/opt/project/data/tropomi/$START_DATE/**/*.nc4"
