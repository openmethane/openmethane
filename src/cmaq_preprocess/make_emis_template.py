#!/usr/bin/env python
# coding: utf-8
"""
make_emis_template.py

Copyright 2023 The Superpower Institute Ltd
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
"""
import os

from fourdvar.util.date_handle import replace_date
from fourdvar.params.template_defn import emis
from fourdvar.params.cmaq_config import met_cro_3d
import numpy as np
import netCDF4 as nc
import datetime

from pathlib import Path


if "PRIOR_REPO_PATH" not in os.environ:
    openMethanePrior = '../../out-om-domain-info.nc'
else:
    openMethanePrior = Path(os.environ["PRIOR_REPO_PATH"]) / 'outputs/out-om-domain-info.nc'

kg2g = 1000. # conversion from kg to g
molarMass = 16. # molar mass of CH4
#attributes that CMAQ is expecting(1)
attrnames = ['IOAPI_VERSION', 'EXEC_ID', 'FTYPE', 'CDATE', 'CTIME', 'WDATE', 'WTIME',
             'SDATE', 'STIME', 'TSTEP', 'NTHIK', 'NCOLS', 'NROWS', 'NLAYS', 'NVARS',
             'GDTYP', 'P_ALP', 'P_BET', 'P_GAM', 'XCENT', 'YCENT', 'XORIG', 'YORIG',
             'XCELL', 'YCELL', 'VGTYP', 'VGTOP', 'VGLVLS', 'GDNAM', 'UPNAM', 'VAR-LIST', 'FILEDESC']
unicodeType = type(u'foo')
nlay = 32
nvar = 1
nz=32 # just surface for the moment
with nc.Dataset(openMethanePrior, mode='r') as input:
    dates = nc.num2date( input['date'][:], input['date'].getncattr('units'), only_use_cftime_datetimes=False)
    emissions = input['OCH4_TOTAL'][...]
cmaqSpecList = ['CH4']
cmaqspec = 'CH4'
for i, date in enumerate(dates):
    met_cro_file = replace_date( met_cro_3d, date)
    with  nc.Dataset( met_cro_file, mode='r') as met_croNC:
        attrDict = {}
        for a in attrnames:
            val = met_croNC.getncattr(a)
            if type(val) == unicodeType:
                val = str(val)
                                ##
            if a=='SDATE':
                attrDict[a]=np.int32(-635)
            elif a=='NVARS':
                attrDict[a]=np.int32(len(cmaqSpecList))
            elif a=='TSTEP':
                attrDict[a]=np.int32(100)
            elif a=='VAR-LIST':
                VarString = "".join([ "{:<16}".format(k) for k in cmaqSpecList ])
                attrDict[a]=VarString
            elif a=='GDNAM':
                attrDict[a]="{:<16}".format('Aus')
            elif a == 'VGLVLS':
                attrDict[a]= val
            else:
                attrDict[a]=val
        lens = {}
        lens['VAR'] = nvar
        lens['LAY'] = nz
        lens['TSTEP'] = 25
        lens['DATE-TIME'] = 2

        outdims = dict()
        domShape = (met_croNC.NROWS, met_croNC.NCOLS)
        if domShape != emissions.shape[-2:]:
            raise ValueError('incompatible dimensions in metcro and emissions')
        for k in met_croNC.dimensions.keys():
            lens[k] = len(met_croNC.dimensions[k])
    # now correct a few of these
    lens['VAR'] = nvar
    lens['LAY'] = nz
    lens['TSTEP'] = 25

    ##  write this to file
    emisFile = replace_date( emis, date)
    with  nc.Dataset(emisFile, mode='w', format='NETCDF4_CLASSIC', clobber=True) as output:
        for k in lens.keys():
            outdims[k] = output.createDimension(k, lens[k])
        outvars = dict()
        outvars['TFLAG'] = output.createVariable('TFLAG', 'i4', ('TSTEP','VAR','DATE-TIME',))
        outvars['TFLAG'].setncattr('long_name',"{:<16}".format('TFLAG'))
        tflag = np.zeros(outvars['TFLAG'].shape, dtype=np.int32) #Peter
        emisyear = date.timetuple().tm_year #Peter
        #print(emisyear)
        emisday=date.timetuple().tm_yday #Peter
        tflag[:,0,0] = 1000*emisyear+emisday #Peter
        # need to set next day which requires care if it's Dec 31
        nextDate = date + datetime.timedelta(1) # add one day
        nextyear = nextDate.timetuple().tm_year #Peter
        nextday=nextDate.timetuple().tm_yday #Peter
        tflag[-1,:,0] = 1000*nextyear+nextday # setting date of last time-slice
        tflag[:,0,1] = (np.arange(lens['TSTEP'])%(lens['TSTEP']-1))*100 # hourly timestep including last timeslice to 0 I hope
        outvars['TFLAG'][...] = tflag
        ## one chunk per layer per time
        outvars[cmaqspec] = output.createVariable(cmaqspec, 'f4', ('TSTEP', 'LAY', 'ROW', 'COL'), zlib = True, shuffle = False, chunksizes = np.array([1,1,domShape[0], domShape[1]]) )
        outvars[cmaqspec].setncattr('long_name',"{:<16}".format(cmaqspec))
        outvars[cmaqspec].setncattr('units',"{:<16}".format("mols/s"))
        outvars[cmaqspec].setncattr('var_desc',"{:<80}".format("Emissions of " + cmaqspec))
        convFac = attrDict['XCELL'] * attrDict['YCELL'] * kg2g/molarMass # from kg/m^2/s to moles/gridcell/s
        outvars[cmaqspec][...] = 0.
        outvars[cmaqspec][:,0,...] = np.stack([convFac*emissions[i,...]]*lens['TSTEP'],axis=0)


        output.setncattr('HISTORY',"")
        # copy other attributes accross
        for k,v in attrDict.items():
            output.setncattr( k, v)
