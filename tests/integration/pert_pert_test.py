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

import numpy as np

import fourdvar._main_driver as main
import fourdvar.datadef as d
import fourdvar.user_driver as user
import fourdvar.util.archive_handle as archive
import fourdvar.util.cmaq_handle as cmaq
from fourdvar import logging
from fourdvar._transform import transform
from fourdvar.params import archive_defn

logger = logging.get_logger(__name__)
logging.setup_logging()

# replace archive directory name and desciption file
archive_defn.experiment = "pert_pert_test"
archive_defn.description = """This is a pert-pert test.
A "true" prior is assumed and a "true" set of observations calculated from it.
A normally distributed perturbation is applied to both the true-prior and the true-obs based of 
their respected uncertainties.
The perturbed prior and perturbed observations are then run through the minimizer to test its 
ability to converge to the expected cost value of n/2 (where n is the number of observations).
"""

# create the true and perturbed input data
prior_true_archive = "prior_true.nc"
prior_pert_archive = "prior_pert.nc"
obs_true_archive = "obs_true.pic.gz"
obs_pert_archive = "obs_pert.pic.gz"

phys_true = user.get_background()
obs_orig = user.get_observed()
model_input = transform(phys_true, d.ModelInputData)
model_output = transform(model_input, d.ModelOutputData)
obs_true = transform(model_output, d.ObservationData)

o_val = obs_true.get_vector()
o_unc = np.array(d.ObservationData.uncertainty)
obs_pert = d.ObservationData(np.random.normal(o_val, o_unc))

unk = transform(phys_true, d.UnknownData)
unk_pert = d.UnknownData(np.random.normal(unk.get_vector(), 1.0) * 0.0)
phys_pert = transform(unk_pert, d.PhysicalData)
model_input_pert = transform(phys_pert, d.ModelInputData)
model_output_pert = transform(model_input_pert, d.ModelOutputData)
simul_pert = transform(model_output_pert, d.ObservationData)

phys_true.archive(prior_true_archive)
phys_pert.archive(prior_pert_archive)
obs_true.archive(obs_true_archive)
simul_pert.archive(obs_pert_archive)

cmaq.wipeout_fwd()

# Output the target cost value for this test
bg_path = os.path.join(archive.get_archive_path(), prior_true_archive)
user.background = d.PhysicalData.from_file(bg_path)
obs_path = os.path.join(archive.get_archive_path(), obs_pert_archive)
user.observed = d.ObservationData.from_file(obs_path)
init_vec = transform(user.background, d.UnknownData).get_vector()
# model_in = transform( user.background, d.ModelInputData)#test_Peter
# model_out = transform( model_in, d.ModelOutputData)#test_Peter
# simulated = transform( model_out, d.ObservationData)#test_Peter
# simulated.archive('simulated_obs.pic.gz')#test_Peter
cost = main.cost_func(init_vec)
logger.info(f"No. obs = {o_val.size}")
logger.info(f"Target cost = {cost}")

# replace current background/prior and observations with perturbed versions.
bg_path = os.path.join(archive.get_archive_path(), prior_pert_archive)
user.background = d.PhysicalData.from_file(bg_path)
obs_path = os.path.join(archive.get_archive_path(), obs_pert_archive)
user.observed = d.ObservationData.from_file(obs_path)

# run minimizer
main.get_answer()
