"""
pert_pert_test.py

Copyright 2016 University of Melbourne.
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
"""

import os
import sys
import numpy as np

import fourdvar as d
from fourdvar._transform import transform
import fourdvar as user
import fourdvar as main
import fourdvar as archive
import fourdvar as archive_defn
import fourdvar as cmaq
import setup_logging
logger = setup_logging.get_logger( __file__ )

# replace archive directory name and description file
archive_defn.experiment = 'emis_sens'
archive_defn.description = """testing emission sensitivities"""
#create the true and perturbed input data
prior_true_archive = 'prior_true.nc'
prior_pert_archive = 'prior_pert.nc'
obs_true_archive = 'obs_true.pic.gz'
obs_pert_archive = 'obs_pert.pic.gz'

phys_true = user.get_background()
obs_orig = user.get_observed()
model_input = transform( phys_true, d.ModelInputData )
model_output = transform( model_input, d.ModelOutputData )
obs_true = transform( model_output, d.ObservationData )

unk = transform( phys_true, d.UnknownData )
unk_pert = d.UnknownData( np.random.normal( unk.get_vector(), 1.0 ) )
phys_pert = transform( unk_pert, d.PhysicalData )
model_pert = transform( phys_pert, d.ModelInputData)

conc_pert = transform(model_pert, d.ModelOutputData)
obs_pert = transform( conc_pert, d.ObservationData)

phys_true.archive( prior_true_archive )
phys_pert.archive( prior_pert_archive )
obs_true.archive( obs_true_archive )
obs_pert.archive( obs_pert_archive )
sys.exit
cmaq.wipeout_fwd()

# Output the target cost value for this test
bg_path = os.path.join( archive.get_archive_path(), prior_pert_archive )
user.background = d.PhysicalData.from_file( bg_path )
obs_path = os.path.join( archive.get_archive_path(), obs_pert_archive )
user.observed = d.ObservationData.from_file( obs_path )
init_vec = transform( user.background, d.UnknownData ).get_vector()
cost = main.cost_func( init_vec )
logger.info( 'No. obs = {:}'.format( o_val.size ) )
logger.info( 'Target cost = {:}'.format( cost ) )

#replace current background/prior and observations with perturbed versions.
bg_path = os.path.join( archive.get_archive_path(), prior_pert_archive )
user.background = d.PhysicalData.from_file( bg_path )
obs_path = os.path.join( archive.get_archive_path(), obs_pert_archive )
user.observed = d.ObservationData.from_file( obs_path )

#run minimizer
main.get_answer()
