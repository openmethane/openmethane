#!/usr/bin/env python
# coding: utf-8

# In[ ]:


##Remap downscaled emissions to the CMAQ domain
##originally written by JDS and modified by NS
##this is an example for regridding dowmscaled CH4 emissions (CH4) to the CMAQ domains
metcro3d = '/scratch/q90/pjr563/openmethane-beta/run-py4dvar/mcip/2019-05-01/d04/METCRO3D_8'

def arealatlon(lat1,lon1,lat2,lon2):
    """Returns the x & y coordinates in meters using a sinusoidal projection"""
    x1=0
    y1=0
    from math import pi, sin, radians
    earth_radius = 6371009 # in meters
    lat10=pi*lat1/180
    lat20=pi*lat2/180
    area=(pi/180)*(earth_radius**2.0)*abs(sin(lat20)-sin(lat10))*abs(lon2-lon1)
    return area

import numpy as np
from netCDF4 import Dataset
import datetime
import numpy.random as random
deflon={'d01':0.65, 'd02':0.22, 'd03':0.071, 'd04':0.0229}
deflat={'d01':0.45, 'd02':0.16, 'd03':0.053, 'd04':0.0178}
## set up the inputs for this function
months=['May']
#domains=['d01','d02','d03','d04']
domains=['d04']
# get WRF sigma levels to make sure they're corrected even if wrong in underlying file
lvls = Dataset( metcro3d).VGLVLS
for imonth, month in enumerate(months): 
    startDate = datetime.datetime(2019,5,1, 0, 0) ## this is the START of the first day
    endDate = datetime.datetime(2019,5,2, 0, 0) ## this is the START of the last day
    ## dfine date range
    ndates = (endDate - startDate).days + 1
    dates = [startDate + datetime.timedelta(days = d) for d in range(ndates)]
#attributes that CMAQ is expecting(1)
attrnames = ['IOAPI_VERSION', 'EXEC_ID', 'FTYPE', 'CDATE', 'CTIME', 'WDATE', 'WTIME',
             'SDATE', 'STIME', 'TSTEP', 'NTHIK', 'NCOLS', 'NROWS', 'NLAYS', 'NVARS',
             'GDTYP', 'P_ALP', 'P_BET', 'P_GAM', 'XCENT', 'YCENT', 'XORIG', 'YORIG',
             'XCELL', 'YCELL', 'VGTYP', 'VGTOP', 'VGLVLS', 'GDNAM', 'UPNAM', 'VAR-LIST', 'FILEDESC']
unicodeType = type(u'foo')
nlay = 1
nvar = 1
nz=lvls.size -1 # lvls are layer boundaries and nz is number layers
lens = {}
lens['VAR'] = nvar
lens['LAY'] = nz
lens['TSTEP'] = 25
lens['DATE-TIME'] = 2
nc =Dataset('/scratch/q90/sa6589/test_Sougol/shared_Sougol/downscaling_out/emission_downscaled_{}.nc'.format(month))
for idate, date in enumerate(dates):
    yyyymmdd_dashed = date.strftime('%Y-%m-%d')
    for idomain, domain in enumerate(domains):
        ## pointer to where we can find the LATD/LOND grid description
        nc2 = Dataset('/scratch/q90/sa6589/test_Sougol/shared_Sougol/GRIDFILE/GRDFILE_{}.nc'.format(domain))
        down_lon=nc['longitude'][...][...]
        down_lat=nc['latitude'][...][...]
        down_ch4=nc['CH4_pop'][...][...]
        emi_lat = nc2['LAT'][...].squeeze()
        emi_lon = nc2['LON'][...].squeeze()
        emi_grdcell=np.zeros_like( emi_lat)
        for i in range(0,emi_lat.shape[0]-1):
            for j in range(0,emi_lat.shape[1]-1):
                maxlon=emi_lon[i,j]+deflon[domain]
                minlon=emi_lon[i,j]-deflon[domain] 
                maxlat=emi_lat[i,j]+deflat[domain]
                minlat=emi_lat[i,j]-deflat[domain]  
                ind_lon=np.asarray(np.where((down_lon<=maxlon) &(down_lon>=minlon))).squeeze()
                ind_lat=np.asarray(np.where((down_lat<=maxlat) & (down_lat>=minlat))).squeeze()

                if((ind_lat.size>0) & (ind_lon.size>0)):
                    maxindlon=ind_lon.max()
                    minindlon=ind_lon.min()
                    maxindlat=ind_lat.max()
                    minindlat=ind_lat.min()
                    #print('hello')
                    unit_factor  =  (1000./16.)
                    #area_jooj=arealatlon(minlat,minlon,maxlat,maxlon)
                    emi_grdcell[i,j]=down_ch4[minindlat:maxindlat,minindlon:maxindlon].sum()*unit_factor
                    #if(emi_grdcell[i,j]>0):
                        #print(emi_grdcell[i,j])

#        month='May'
        emisfolder ='/scratch/q90/pjr563/openmethane-beta/run_cmaq/{}/{}'.format(yyyymmdd_dashed,domain)

        dt = date.timetuple()
        emisfile = f'emis_record_{dt.tm_year:4d}{dt.tm_mon:02d}{dt.tm_mday:02d}.nc'
        grdem = Dataset(emisfile, mode='w', format='NETCDF4_CLASSIC', clobber=True)    
        outdims = dict()
        domShape = nc2['LAT'][...].squeeze().shape

        ## the main function in the script


        for k in nc2.dimensions.keys():
            lens[k] = len(nc2.dimensions[k])
# now correct a few of these
        lens['VAR'] = nvar
        lens['LAY'] = nz
        lens['TSTEP'] = 25

            ## get ready to write this to file

        for k in lens.keys():
            outdims[k] = grdem.createDimension(k, lens[k])
        cmaqSpecList = ['CH4']
        cmaqspec = 'CH4'
        outvars = dict()
        outvars['TFLAG'] = grdem.createVariable('TFLAG', 'i4', ('TSTEP','VAR','DATE-TIME',))
        outvars['TFLAG'].setncattr('long_name',"{:<16}".format('TFLAG'))
        tflag = np.zeros(outvars['TFLAG'].shape, dtype=np.int32) #Peter
        emisyear = date.timetuple().tm_year #Peter
        #print(emisyear)
        emisday=date.timetuple().tm_yday #Peter
        tflag[:,0,0] = 1000*emisyear+emisday #Peter
        # need to set next day which requires care if it's Dec 31
        nextDate = date + datetime.timedelta(1) # add one day
        nextyear = date.timetuple().tm_year #Peter
        nextday=date.timetuple().tm_yday #Peter
        tflag[-1,:,0] = 1000*nextyear+nextday # setting date of last time-slice
        tflag[:,0,1] = (np.arange(lens['TSTEP'])%(lens['TSTEP']-1))*100 # hourly timestep including last timeslice to 0 I hope
        outvars['TFLAG'][...] = tflag
        ## one chunk per layer per time
        outvars[cmaqspec] = grdem.createVariable(cmaqspec, 'f4', ('TSTEP', 'LAY', 'ROW', 'COL'), zlib = True, shuffle = False, chunksizes = np.array([1,1,domShape[0], domShape[1]]) )
        outvars[cmaqspec].setncattr('long_name',"{:<16}".format(cmaqspec))
        outvars[cmaqspec].setncattr('units',"{:<16}".format("mols/s"))
        outvars[cmaqspec].setncattr('var_desc',"{:<80}".format("Emissions of " + cmaqspec))
        outvars[cmaqspec][...] = 0.
        emi_grdcell = random.uniform(low=0., high=emi_grdcell.max(), size=emi_grdcell.shape)
        outvars[cmaqspec][:,0,...] = np.stack([emi_grdcell]*lens['TSTEP'],axis=0)

        for a in attrnames:
            val = nc2.getncattr(a)
            if type(val) == unicodeType:
                #print('ddd')
                val = str(val)
                                ##
            if a=='SDATE':
                grdem.setncattr(a,np.int32(-635))
            elif a=='NVARS':
                grdem.setncattr(a,np.int32(len(cmaqSpecList)))
            elif a=='TSTEP':
                grdem.setncattr(a,np.int32(100))   
            elif a=='VAR-LIST':
                VarString = "".join([ "{:<16}".format(k) for k in cmaqSpecList ])
                grdem.setncattr(a,VarString)
            elif a=='GDNAM':
                grdem.setncattr(a,"{:<16}".format('Aus'))
            elif a == 'VGLVLS':
                grdem.setncattr(a, lvls)

            else:
                grdem.setncattr(a,val)
                                
        grdem.setncattr('HISTORY',"")
        #grdem.setncattr('SDATE',np.int32(-635))
        #grdem.setncattr('TSTEP',numpy.int32(100))
        grdem.close()
        nc2.close()



