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
def mapObs( obsFileName):
    """ extracts position and value for py4dvar observations, returns number of obs per gridcell and their mean.
    Input: file name for py4dvar obs structure.
    outputs: obsCount: numpy int array of number of obs per py4dvar gridcell
    obsMean: mean of obs in each py4dvar gridcell. Returns 0 if no obs """
    obsList = fh.load_list( obsFileName )
    domain = obsList.pop(0)
    obsCount = np.zeros((domain['NROWS'], domain['NCOLS']))
    obsMean = np.zeros_like( obsCount)
    obsMeanSq = np.zeros_like( obsCount)
    for ob in  obsList:
        obsCount[ ob['lite_coord'][3:5]] +=1
        obsMean[ ob['lite_coord'][3:5]] += ob['value']
        obsMeanSq[ ob['lite_coord'][3:5]] += ob['value']**2
    hasObs = ( obsCount > 0.5) # at least one observation
    obsMean[ hasObs] /=  obsCount[ hasObs] # avoiding 0/0 error
    obsMeanSq[ hasObs] /=  obsCount[ hasObs] # avoiding 0/0 error
    return obsCount, obsMean, obsMeanSq