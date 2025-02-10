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
import glob

from fourdvar.env import env
from postproc import alerts
from util import archive


def main():
    domain_file = env.path('ALERTS_DOMAIN_FILE', default='om-domain-info.nc')
    dir_glob = env.str('ALERTS_BASELINE_DIRS', default=None)
    dir_list = sorted(glob.glob(dir_glob))
    if dir_list is None:
        raise ValueError('must specify environment variable ALERTS_BASELINE_DIRS')
    obs_file_template = env.str('ALERTS_OBS_FILE_TEMPLATE', default='input/test_obs.pic.gz')
    sim_file_template = env.str('ALERTS_SIM_FILE_TEMPLATE', default='simulobs.pic.gz')
    near_threshold = env.float('ALERTS_NEAR_THRESHOLD', 0.2)
    far_threshold = env.float('ALERTS_FAR_THRESHOLD', 1.0)
    output_file = env.str('ALERTS_BASELINE_FILE', default='alerts_baseline.nc')

    archive.baseline(
        daily_s3_bucket=os.getenv('TARGET_BUCKET'),
        end_date=env.date("END_DATE"),
        domain_name=env.str("DOMAIN_NAME"),
        local_path=env.path("STORE_PATH"),
        baseline_length_days=env.int("BASELINE_LENGTH_DAYS", 365),
    )

    alerts.create_alerts_baseline(
        domain_file = domain_file,
        dir_list = dir_list,
        obs_file_template = obs_file_template,
        sim_file_template = sim_file_template,
        near_threshold = near_threshold,
        far_threshold = far_threshold,
        output_file = output_file,
    )

    
if __name__ == "__main__":
    main()
