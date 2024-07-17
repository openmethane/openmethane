#
# Copyright 2023 The Superpower Institute Ltd
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

import fourdvar.datadef as d
from fourdvar._transform import transform
from fourdvar.params.input_defn import prior_file
from fourdvar.params.root_path_defn import store_path


def run_daily_flow():
    physical = d.PhysicalData.from_file(prior_file)
    model_input = transform(physical, d.ModelInputData)
    model_output = transform(model_input, d.ModelOutputData)
    # observed = d.ObservationData.from_file(obs_file)
    # simulated_observations = d.ObservationData.from_file( simulFile )
    # model_input.archive('/scratch/q90/cm5310/plotting/model_input')
    simulated_observations = transform(model_output, d.ObservationData)
    simulated_observations.archive(os.path.join(store_path, "simulobs.pic.gz"))


if __name__ == "__main__":
    run_daily_flow()
