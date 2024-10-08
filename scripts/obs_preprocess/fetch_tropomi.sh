#!/bin/bash
# """
# fetch_tropomi.sh
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

export START_DATE=${START_DATE:-2022-07-22}
export END_DATE=${END_DATE:-2022-07-22} # Only running a single day

python scripts/obs_preprocess/fetch_tropomi.py \
      -c config/obs_preprocess/config.json \
      -s ${START_DATE} \
      -e ${END_DATE}T23:59:59 \
      "/opt/project/data/tropomi/$START_DATE"