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
import dotenv
import glob
from postproc import alerts

def main():
    dotenv.load_dotenv()
    domain_file = os.getenv('ALERTS_DOMAIN_FILE', default='om-domain-info.nc')
    dir_glob = os.getenv('ALERTS_BASELINE_DIRS', default=None)
    dir_list = sorted(glob.glob( dir_glob))
    if dir_list is None:
        raise ValueError('must specify environment variable ALERTS_BASELINE_DIRS')
    obs_file_template = os.getenv('ALERTS_OBS_FILE_TEMPLATE', default='input/test_obs.pic.gz')
    sim_file_template = os.getenv('ALERTS_SIM_FILE_TEMPLATE', default='simulobs.pic.gz')
    output_file = os.getenv('ALERTS_OUTPUT_FILE', default='alerts_baseline.nc')
    alerts.create_alerts_baseline(
        domain_file = domain_file,
        dir_list = dir_list,
        obs_file_template = obs_file_template,
        sim_file_template = sim_file_template,
        output_file = output_file,
    )

    
if __name__ == "__main__":
    main()
