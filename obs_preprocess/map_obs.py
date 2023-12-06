"""
map_obs.py

Copyright 2023 The Superpower Institute Ltd
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
"""
import numpy as np
import context
import os
import sys
from fourdvar.params.input_defn import  obs_file
from fourdvar.util import file_handle as fh

import matplotlib.pyplot as plt
obsList = fh.load_list( obs_file )
domain = obsList.pop(0)
obsCount = np.zeros((domain['NROWS'], domain['NCOLS']))
obsMean = np.zeros_like( obsCount)
for ob in  obsList:
    obsCount[ ob['lite_coord'][3:5]] +=1
    obsMean[ ob['lite_coord'][3:5]] += ob['value']
hasObs = ( obsCount > 0.5) # at least one observation
obsMean[ hasObs] /=  obsCount[ hasObs] # avoiding 0/0 error
obsCount.dump('obsCount.pic')
obsMean.dump('obsMean.pic')
