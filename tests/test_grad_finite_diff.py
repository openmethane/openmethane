"""
test_grad_finite_diff.py

Copyright 2023 the Superpower Inistitute
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
"""
import os
import time
import numpy as np
import pickle as pickle

import context
import fourdvar.user_driver as user
import fourdvar._main_driver as main
import fourdvar.datadef as d
from fourdvar._transform import transform
import fourdvar.util.archive_handle as archive
import fourdvar.params.archive_defn as archive_defn
import fourdvar.util.cmaq_handle as cmaq

archive_defn.experiment = 'tmp_grad_finite_diff'
archive_defn.desc_name = ''

archive_path = archive.get_archive_path()
print('saving results in:\n{}'.format(archive_path))


print('get prior in PhysicalData format')
st = time.time()
prior_phys = user.get_background()
print('completed in {}s'.format( int(time.time() - st) ))
prior_phys.archive( 'prior.ncf' )
print('archived.')
print('get observations in ObservationData format')
st = time.time()
observed = user.get_observed()
print('completed in {}s'.format( int(time.time() - st) ))
observed.archive( 'observed.pickle' )
print('archived.')

print('convert prior into UnknownData format')
st = time.time()
prior_unknown = transform( prior_phys, d.UnknownData )
print('completed in {}s'.format( int(time.time() - st) ))

print('get unknowns in vector form.')
st = time.time()
prior_vector = prior_unknown.get_vector()
print('completed in {}s'.format( int(time.time() - st) ))

initCost = main.cost_func( prior_vector)
initGrad = main.gradient_func( prior_vector)

epsilon = 1e-6
dx =  epsilon*np.random.normal( 0.0, 1.0, prior_vector.shape )
pertCost = main.cost_func( prior_vector + dx)
print(('finite difference', pertCost -initCost))
print(('grad calc', dx*initGrad))
print('FINISHED!')
