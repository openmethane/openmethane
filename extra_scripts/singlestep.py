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
from fourdvar.params.root_path_defn import store_path
from fourdvar.params.input_defn import prior_file, obs_file


physical = d.PhysicalData.from_file( prior_file)
modelInput = transform( physical, d.ModelInputData)
modelOutput = transform( modelInput, d.ModelOutputData)
observed = d.ObservationData.from_file( obs_file)
#simul = d.ObservationData.from_file( simulFile )
#modelInput.archive('/scratch/q90/cm5310/plotting/model_input')
simul = transform( modelOutput, d.ObservationData)
simul.archive( os.path.join(store_path, 'simulobs.pic.gz'))
residual = d.ObservationData.get_residual(observed, simul)
#residual.archive('/scratch/q90/cm5310/plotting/residual')
#simul.archive('/scratch/q90/cm5310/plotting/simulations.pickle')
w_residual = d.ObservationData.error_weight( residual )
adj_forcing = transform( w_residual, d.AdjointForcingData )
sensitivity = transform( adj_forcing, d.SensitivityData )
phys_sense = transform( sensitivity, d.PhysicalAdjointData )
un_gradient = transform( phys_sense, d.UnknownData )
        
