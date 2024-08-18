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

import os
import pickle
import time

import numpy as np

import fourdvar.datadef as d
import fourdvar.user_driver as user
import fourdvar.util.archive_handle as archive
import fourdvar.util.cmaq_handle as cmaq
from fourdvar._transform import transform
from fourdvar.params import archive_defn


def test_fourdvar_grad_verbose(target_environment):
    # Settings are modified locally so this resets them to the default initially
    target_environment("docker-test")

    _run_grad_verbose()


def _run_grad_verbose():
    archive_defn.experiment = "tmp_grad_verbose"
    archive_defn.desc_name = ""

    archive_path = archive.get_archive_path()
    print(f"saving results in: {archive_path}")

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

    print("perturb vector to produce mock input for gradient_func")
    st = time.time()
    test_vector = prior_vector + np.random.normal(0.0, 1.0, prior_vector.shape)
    print(f"completed in {int(time.time() - st)}s")

    print("\ncopy logic of gradient function.\n")

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

    print("calculate adjoint forcing from weighted residuals")
    st = time.time()
    adj_frc = transform(weighted, d.AdjointForcingData)
    print(f"completed in {int(time.time() - st)}s")
    adj_frc.archive("adjoint_model_input")
    print("archived.")

    print("run adjoint model (get sensitivities)")
    st = time.time()
    sensitivity = transform(adj_frc, d.SensitivityData)
    print(f"completed in {int(time.time() - st)}s")
    sensitivity.archive("adjoint_model_output")
    print("archived.")

    print("convert sensitivities into PhysicalAdjointData format")
    st = time.time()
    phys_sens = transform(sensitivity, d.PhysicalAdjointData)
    print(f"completed in {int(time.time() - st)}s")
    phys_sens.archive("physical_sensitivity.ncf")
    print("archived.")

    print("convert sensitivity into gradient vector")
    st = time.time()
    gradient = transform(phys_sens, d.UnknownData).get_vector()
    print(f"completed in {int(time.time() - st)}s")

    print("calculate and record least squares cost gradient")
    st = time.time()
    gradient += test_vector - prior_vector
    fname = os.path.join(archive_path, "gradient.pickle")
    with open(fname, "wb") as f:
        pickle.dump(gradient, f)
    print(f"success in {int(time.time() - st)}s. gradient saved in {fname}")

    print("cleanup files produced by CMAQ")
    cmaq.wipeout_fwd()


if __name__ == "__main__":
    _run_grad_verbose()
