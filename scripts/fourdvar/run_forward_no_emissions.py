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
"""Run the forward model with the prior emissions zeroed.

`run_daily_step.py` with one change: every emission is set to zero before the
transform chain, so the simulated columns carry only the boundary and initial
conditions. Differencing the two runs gives the concentration the prior
emissions contribute, per sounding.

The forward model is linear in emissions over a month of CH4, so that
difference is exact, and it bounds what the inversion's multiplier field can
do: the control variable scales these emissions, so it cannot generate spatial
structure the difference does not already contain.

`cmaq_preprocess.bias.calculate_emissions_bias` does the same zeroing to report
a domain mean. This keeps the simulated observations instead of reducing them.
"""

import os

import openmethane.fourdvar.datadef as d
import openmethane.fourdvar.util.cmaq_handle as cmaq
from openmethane.fourdvar._transform import transform
from openmethane.fourdvar.params.input_defn import obs_file, prior_file
from openmethane.fourdvar.params.root_path_defn import store_path
from openmethane.util.logger import get_logger

logger = get_logger(__name__)


def run_forward_no_emissions():
    physical = d.PhysicalData.from_file(prior_file)
    for species in physical.emis:
        physical.emis[species] *= 0.0  # zeroing emissions while preserving shape
    logger.info(f"zeroed emissions for {sorted(physical.emis)}")

    # no adjoint run follows, and on the full domain the checkpoints dominate
    # the runtime
    with cmaq.checkpointing_disabled():
        model_input = transform(physical, d.ModelInputData)
        model_output = transform(model_input, d.ModelOutputData)

        # Observations must be read in even though they aren't directly used
        observed = d.ObservationData.from_file(obs_file)  # noqa: F841

        simulated_observations = transform(model_output, d.ObservationData)

    simulated_observations.archive(os.path.join(store_path, "simulobs.pic.gz"))


if __name__ == "__main__":
    run_forward_no_emissions()
