#
# Copyright 2025 The Superpower Institute Ltd
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

import logging

from fourdvar.env import env
from postproc import alerts

def main():
    baseline_file = env.path('ALERTS_BASELINE_FILE', default='alerts_baseline.nc')
    daily_dir = env.path('ALERTS_DAILY_DIR', default=None) or env.path('STORE_PATH', default=None)
    if daily_dir is None:
        raise ValueError('must specify environment variable ALERTS_DAILY_DIR')
    obs_file_template = env.str('ALERTS_OBS_FILE_TEMPLATE', default='input/test_obs.pic.gz')
    sim_file_template = env.str('ALERTS_SIM_FILE_TEMPLATE', default='simulobs.pic.gz')
    output_file = env.str('ALERTS_OUTPUT_FILE', default='alerts.nc')
    alerts_threshold = env.float( 'ALERTS_THRESHOLD', default=5.0)
    significance_threshold = env.float( 'SIGNIFICANCE_THRESHOLD', default=3.0)
    count_threshold = env.int("ALERTS_COUNT_THRESHOLD", 30)

    alerts.create_alerts(
        baseline_file = baseline_file,
        daily_dir = daily_dir,
        obs_file_template = obs_file_template,
        sim_file_template = sim_file_template,
        output_file = output_file,
        alerts_threshold = alerts_threshold,
        significance_threshold=significance_threshold,
        count_threshold = count_threshold,
    )

    
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
