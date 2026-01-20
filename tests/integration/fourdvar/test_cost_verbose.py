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
import time

import numpy as np

import openmethane.fourdvar.datadef as d
import openmethane.fourdvar.user_driver as user
import openmethane.fourdvar.util.archive_handle as archive
import openmethane.fourdvar.util.cmaq_handle as cmaq
from openmethane.fourdvar._transform import transform
from openmethane.fourdvar.params import archive_defn


def test_fourdvar_cost_verbose(target_environment):
    # Settings are modified locally so this resets them to the default initially
    target_environment("docker-test")
    _run_cost_verbose()


def _run_cost_verbose():
    archive_defn.experiment = "tmp_cost_verbose"
    archive_defn.desc_name = ""

    archive_path = archive.get_archive_path()
    print(f"saving results in:\n{archive_path}")

    print("get observations in ObservationData format")
    st = time.time()
    observed = user.get_observed()
    print(f"completed in {int(time.time() - st)}s")
    observed.archive("observed.pickle")
    print("archived.")

    print("get prior in PhysicalData format")
    st = time.time()
    prior_phys = user.get_background()
    print(f"completed in {int(time.time() - st)}s")
    prior_phys.archive("prior.ncf")
    print("archived.")

    print("convert prior into UnknownData format")
    st = time.time()
    prior_unknown = transform(prior_phys, d.UnknownData)
    print(f"completed in {int(time.time() - st)}s")

    print("get unknowns in vector form.")
    st = time.time()
    prior_vector = prior_unknown.get_vector()
    print(f"completed in {int(time.time() - st)}s")

    print("perturb vector to produce mock input for cost_func")
    st = time.time()
    # test_vector = prior_vector + np.random.normal( 0.0, 1.0, prior_vector.shape )
    test_vector = prior_vector
    print(f"completed in {int(time.time() - st)}s")

    print("\ncopy logic of least squares cost function.\n")

    print("convert input vector into UnknownData format")
    st = time.time()
    unknown = d.UnknownData(test_vector)
    print(f"completed in {int(time.time() - st)}s")

    print("convert new unknowns into PhysicalData format")
    st = time.time()
    physical = transform(unknown, d.PhysicalData)
    print(f"completed in {int(time.time() - st)}s")
    physical.archive("new_physical.ncf")
    print("archived.")

    print("convert physical into ModelInputData")
    st = time.time()
    model_in = transform(physical, d.ModelInputData)
    print(f"completed in {int(time.time() - st)}s")
    model_in.archive("forward_model_input")
    print("archived.")

    print("run forward model (get concentrations)")
    st = time.time()
    model_out = transform(model_in, d.ModelOutputData)
    print(f"completed in {int(time.time() - st)}s")
    model_out.archive("forward_model_output")
    print("archived.")

    print("get simulated observations from concentrations")
    st = time.time()
    simulated = transform(model_out, d.ObservationData)
    print(f"completed in {int(time.time() - st)}s")
    simulated.archive("simulated_observations.pickle")
    print("archived.")

    print("calculate residual of observations")
    st = time.time()
    residual = d.ObservationData.get_residual(observed, simulated)
    print(f"completed in {int(time.time() - st)}s")
    residual.archive("observation_residuals.pickle")
    print("archived.")

    print("weight residual by inverse error covariance")
    st = time.time()
    weighted = d.ObservationData.error_weight(residual)
    print(f"completed in {int(time.time() - st)}s")
    weighted.archive("weighted_residuals.pickle")
    print("archived.")

    print("calculate and show least squares cost")
    st = time.time()
    cost = 0.5 * np.sum((test_vector - prior_vector) ** 2)
    cost += 0.5 * np.sum(residual.get_vector() * weighted.get_vector())
    print(f"success in {int(time.time() - st)}s. cost = {cost}")

    print("cleanup files produced by CMAQ")
    cmaq.wipeout_fwd()


if __name__ == "__main__":
    _run_cost_verbose()
