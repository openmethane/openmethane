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
import os
import pathlib
import dotenv

from postproc import alerts

def main():
    dotenv.load_dotenv()
    baseline_file = os.getenv('ALERTS_BASELINE_FILE', default='alerts_baseline.nc')
    daily_dir = os.getenv('ALERTS_DAILY_DIR', default=None)
    if daily_dir is None:
        raise ValueError('must specify environment variable ALERTS_DAILY_DIR')
    obs_file_template = os.getenv('ALERTS_OBS_FILE_TEMPLATE', default='input/test_obs.pic.gz')
    sim_file_template = os.getenv('ALERTS_SIM_FILE_TEMPLATE', default='simulobs.pic.gz')
    output_file = os.getenv('ALERTS_OUTPUT_FILE', default='alerts.nc')
    alerts_threshold = float(os.getenv( 'ALERTS_THRESHOLD', default='0.0'))
    significance_threshold = float(os.getenv( 'SIGNIFICANCE_THRESHOLD', default='2.0'))
    alerts.create_alerts(
        baseline_file = pathlib.Path(baseline_file),
        daily_dir = pathlib.Path(daily_dir),
        obs_file_template = obs_file_template,
        sim_file_template = sim_file_template,
        output_file = output_file,
        alerts_threshold = alerts_threshold,
        significance_threshold=significance_threshold,
    )

    
if __name__ == "__main__":
    main()
