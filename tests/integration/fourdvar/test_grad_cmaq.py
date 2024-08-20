#
# Copyright 2023 The SuperPower Institute Ltd
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

import fourdvar._main_driver as main
import fourdvar.datadef as d
import fourdvar.user_driver as user
import fourdvar.util.archive_handle as archive
from fourdvar._transform import transform
from fourdvar.params import archive_defn


def test_fourdvar_grad_cmaq(target_environment):
    target_environment("docker-test")

    _run_grad_cmaq()


def _run_grad_cmaq():
    archive_defn.experiment = "tmp_grad_cmaq"
    archive_defn.desc_name = ""

    archive_path = archive.get_archive_path()
    print(f"saving results in:\n{archive_path}")

    print("get prior in PhysicalData format")
    physical = user.get_background()
    prior_phys.archive("prior.ncf")
    modelInput = transform(physical, d.ModelInputData)
    modelOutput = transform(modelInput, d.ModelOutputData)

    initGrad = main.gradient_func(prior_vector)

    epsilon = 1e-3
    dx = epsilon * np.random.normal(0.0, 1.0, prior_vector.shape)
    pertCost = main.cost_func(prior_vector + dx)
    print("pertCost", pertCost)
    print(("finite difference", pertCost - initCost))
    print(("grad calc", np.dot(dx, initGrad)))


if __name__ == "__main__":
    _run_grad_cmaq()
