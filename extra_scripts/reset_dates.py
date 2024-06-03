#!/usr/bin/env python
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

"""Script to ensure dates in prior_file and obs_file conform with date_defn."""

import datetime
import subprocess

from fourdvar.params.date_defn import end_date, start_date
from fourdvar.params.input_defn import obs_file, prior_file
from fourdvar.util.file_handle import load_list, save_list


sdate =  datetime.date( start_date // 10000, (start_date // 100) % 100, start_date % 100)
edate =  datetime.date( end_date // 10000, (end_date // 100) % 100, end_date % 100)
inObs = load_list( obs_file)
outObs = [ inObs.pop(0)] # first element
outObs[0]['SDATE'] = start_date
outObs[0]['EDATE'] = end_date
outObs += [o for o in inObs if o['time'].date() >= sdate and o['time'].date() <= edate]
save_list( outObs, obs_file.replace('.gz','_reset.gz'))

SDATE = 1000*sdate.timetuple().tm_year + sdate.timetuple().tm_yday
EDATE = 1000*edate.timetuple().tm_year + edate.timetuple().tm_yday

command = f'ncatted -O -a TDAY,emis,m,l,{EDATE-SDATE+1} -a SDATE,global,m,l,{SDATE} -a EDATE,global,m,l,{EDATE} {prior_file} {prior_file}.reset'
print('\t\t\t'+command)
commandList = command.split(' ')        
##
p = subprocess.Popen(commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
stdout, stderr = p.communicate()
if len(stderr) > 0:
    print("stdout = " + stdout)
    print("stderr = " + stderr)
    raise RuntimeError("Error from atted...")
