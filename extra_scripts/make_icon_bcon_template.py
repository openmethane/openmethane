tmake_icon_bcon_template.py

Copyright 2023 The Superpower Institute Ltd
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
"""
import numpy as np
import netCDF4 as nc
cmaqSpecList = ['CH4']
cmaqspec = 'CH4'

iconFile = 'icon.nc'
bconFile = 'bcon.nc'
iconTemplate = 'ICON.d01.W.CH4only.nc'
met_cro_file = '/home/unimelb.edu.au/prayner/Dropbox/openmethane-beta/mcip/2022-07-01/d01/METCRO3D_1'
attrnames = ['IOAPI_VERSION', 'EXEC_ID', 'FTYPE', 'CDATE', 'CTIME', 'WDATE', 'WTIME',
             'SDATE', 'STIME', 'TSTEP', 'NTHIK', 'NCOLS', 'NROWS', 'NLAYS', 'NVARS',
             'GDTYP', 'P_ALP', 'P_BET', 'P_GAM', 'XCENT', 'YCENT', 'XORIG', 'YORIG',
             'XCELL', 'YCELL', 'VGTYP', 'VGTOP', 'VGLVLS', 'GDNAM', 'UPNAM', 'VAR-LIST', 'FILEDESC']
unicodeType = type(u'foo')
nlay = 32
nvar = 1
nz=32 # just surface for the moment
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
            attrDict[a]=np.int32( 0)
        elif a=='VAR-LIST':
            VarString = "".join([ "{:<16}".format(k) for k in cmaqSpecList ])
            attrDict[a]=VarString
        elif a=='GDNAM':
            attrDict[a]="{:<16}".format('Aus')
        elif a == 'UPNAM':
            attrDict[a] = "{:<16}".format("OPN_BC_FILE")
        elif a == 'FTYPE':
            attrDict[a] = np.int32(2)
        elif a == 'VGLVLS':
            attrDict[a]= val
        else:
            attrDict[a]=val
    lens = {}
    lens['VAR'] = nvar
    lens['LAY'] = nz
    lens['TSTEP'] = 1
    lens['DATE-TIME'] = 2

    outdims = dict()
    domShape = (met_croNC.NROWS, met_croNC.NCOLS)
    for k in met_croNC.dimensions.keys():
        lens[k] = len(met_croNC.dimensions[k])
# now correct a few of these
lens['VAR'] = nvar
lens['LAY'] = nz
lens['TSTEP'] = 1


with nc.Dataset( iconFile, 'w') as output:
    outdims = dict()
    for k in lens.keys():
        outdims[k] = output.createDimension(k, lens[k])
    outvars = dict()
    outvars['TFLAG'] = output.createVariable('TFLAG', 'i4', ('TSTEP','VAR','DATE-TIME',))
    outvars['TFLAG'].setncattr('long_name',"{:16}".format('TFLAG'))
    outvars['TFLAG'].setncattr('units',"{:16}".format('<YYYYDDD,HHMMSS>'))
    outvars['TFLAG'].setncattr('var_desc',"{:80}".format('Timestep-valid flags:  (1) YYYYDDD or (2) HHMMSS                                '))
    tflag = np.zeros(outvars['TFLAG'].shape, dtype=np.int32) 
    tflag[:,0,0] = 0
    outvars['TFLAG'][...] = tflag
    ## one chunk per layer per time
    outvars[cmaqspec] = output.createVariable(cmaqspec, 'f4', ('TSTEP', 'LAY', 'ROW', 'COL'), zlib = True, shuffle = False)
    outvars[cmaqspec].setncattr('long_name',"{:<16}".format(cmaqspec))
    outvars[cmaqspec].setncattr('units',"{:<16}".format("mols/s"))
    outvars[cmaqspec].setncattr('var_desc',"{:<80}".format("Emissions of " + cmaqspec))
    outvars[cmaqspec][...] = 1.84


    output.setncattr('HISTORY',"")
    # copy other attributes accross
    for k,v in attrDict.items(): output.setncattr( k, v)

with nc.Dataset( bconFile, 'w') as output:
    outdims = dict()
    lens['PERIM'] = 2*( lens['ROW'] +2) +2*lens['COL']
    for k in lens.keys():
        outdims[k] = output.createDimension(k, lens[k])
    outvars = dict()
    outvars['TFLAG'] = output.createVariable('TFLAG', 'i4', ('TSTEP','VAR','DATE-TIME',))
    outvars['TFLAG'].setncattr('long_name',"{:<16}".format('TFLAG'))
    tflag = np.zeros(outvars['TFLAG'].shape, dtype=np.int32) 
    tflag[:,0,0] = 0
    outvars['TFLAG'][...] = tflag
    ## one chunk per layer per time
    outvars[cmaqspec] = output.createVariable(cmaqspec, 'f4', ('TSTEP', 'LAY', 'PERIM'), zlib = True, shuffle = False)
    outvars[cmaqspec].setncattr('long_name',"{:<16}".format(cmaqspec))
    outvars[cmaqspec].setncattr('units',"{:<16}".format("mols/s"))
    outvars[cmaqspec].setncattr('var_desc',"{:<80}".format("boundary value of " + cmaqspec))
    outvars[cmaqspec][...] = 1.84


    output.setncattr('HISTORY',"")
    # copy other attributes accross
    for k,v in attrDict.items(): output.setncattr( k, v)

