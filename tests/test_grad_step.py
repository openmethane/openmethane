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

import numpy as np

import fourdvar.datadef as d
from fourdvar._transform import transform
from fourdvar.params.input_defn import obs_file, prior_file

physical = d.PhysicalData.from_file(prior_file)
unknown = transform(physical, d.UnknownData)
# physical.emis['CH4'][...] = 0.
# physical.emis['CH4'][0,0,56,152]=1.
modelInput = transform(physical, d.ModelInputData)
priInput = modelInput.get_vector()
# test=d.ModelInputData.load_from_vector_template( priInput)
# initCost = modelInput.sum_squares()


# sensitivity = d.SensitivityData.create_from_ModelInputData()
modelOutput = transform(modelInput, d.ModelOutputData)
priOutput = modelOutput.get_vector()
observed = d.ObservationData.from_file(obs_file)
# simul = d.ObservationData.from_file( simulFile )
# modelInput.archive('/scratch/q90/cm5310/plotting/model_input')
simul = transform(modelOutput, d.ObservationData)
initCost = (
    0.5
    * (
        ((np.array(simul.value) - np.array(observed.value)) / np.array(observed.uncertainty)) ** 2
    ).sum()
)
print("initCost", initCost)
# simul.archive( os.path.join(store_path, 'simulobs.pic.gz'))
residual = d.ObservationData.get_residual(observed, simul)
# #residual.archive('/scratch/q90/cm5310/plotting/residual')
# #simul.archive('/scratch/q90/cm5310/plotting/simulations.pickle')
w_residual = d.ObservationData.error_weight(residual)
adj_forcing = transform(w_residual, d.AdjointForcingData)
sensitivity = transform(adj_forcing, d.SensitivityData)
sensVec = sensitivity.get_vector()
phys_sense = transform(sensitivity, d.PhysicalAdjointData)
un_gradient = transform(phys_sense, d.UnknownData)

# now perturb unknown vector
prior_unknown = transform(physical, d.UnknownData)
prior_vector = prior_unknown.get_vector()
epsilon = 1e-2
dx = epsilon * np.random.normal(0.0, 1.0, prior_vector.shape)
dx[-8:] = 0.0  # remove BC
# dx[:]=0. # 0 it
# dx[ 56*174+152] = 0.01
pert_unknown = d.UnknownData(prior_vector + dx)
pert_physical = transform(pert_unknown, d.PhysicalData)
pert_model_input = transform(pert_physical, d.ModelInputData)
pertInput = pert_model_input.get_vector()
pert_model_output = transform(pert_model_input, d.ModelOutputData)
pertOutput = pert_model_output.get_vector()
# pertCost=pert_model_output.sum_squares()
pert_simul = transform(pert_model_output, d.ObservationData)
pertObsCost = (
    0.5
    * (
        ((np.array(pert_simul.value) - np.array(observed.value)) / np.array(observed.uncertainty))
        ** 2
    ).sum()
)

pertBgCost = 0.5 * (dx**2).sum()
pertCost = pertObsCost + pertBgCost
print("pertCost", pertCost)
print("finite diff", pertCost - initCost)
print(" gradient calc", np.dot(un_gradient.get_vector(), dx))
