#!/usr/bin/env python
# coding: utf-8

# In[ ]:


##Remap downscaled emissions to the CMAQ domain
##originally written by JDS and modified by NS
##this is an example for regridding dowmscaled CH4 emissions (CH4) to the CMAQ domains


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
deflon=0
deflat=0
## set up the inputs for this function
months=['May']
domains=['d01','d02','d03','d04']
#domains=['d04']
for imonth, month in enumerate(months): 
    startDate = datetime.datetime(2019,5,1, 0, 0) ## this is the START of the first day
    endDate = datetime.datetime(2019,5,2, 0, 0) ## this is the START of the last day
    ## dfine date range
    ndates = (endDate - startDate).days + 1
    dates = [startDate + datetime.timedelta(days = d) for d in range(ndates)]
for idate, date in enumerate(dates):
    yyyymmdd_dashed = date.strftime('%Y-%m-%d')
    for idomain, domain in enumerate(domains):
            nc2 = Dataset('/scratch/q90/sa6589/test_Sougol/shared_Sougol/GRIDFILE/GRDFILE_{}.nc'.format(domain))
           # Extend_i1_i1=np.zeros(shape=2,dtype=float)
           # Extend_i1_im1=np.zeros(shape=2,dtype=float)
           # Extend_im1_im1=np.zeros(shape=2,dtype=float)
           # Extend_im1_i1=np.zeros(shape=2,dtype=float)
           ## pointer to where we can find the LATD/LOND grid description
            nc =Dataset('/scratch/q90/sa6589/test_Sougol/shared_Sougol/downscaling_out/emission_downscaled_{}.nc'.format(month))
            down_lon=nc['longitude'][...]
            down_lat=nc['latitude'][...]
            ch4_down=nc['CH4_pop'][...]
#Area_grdcell=np.zeros(shape=[nc2['LAT'][...].squeeze().shape[0],nc2['LAT'][...].squeeze().shape[1]],dtype=float)
            emi_grdcell=np.zeros(shape=[nc2['LAT'][...].squeeze().shape[0],nc2['LAT'][...].squeeze().shape[1]],dtype=float)
            for i in range(0,nc2['LON'][...].squeeze().shape[0]-1):
                for j in range(0,nc2['LAT'][...].squeeze().shape[1]-1):
                    #maxlon=max(nc2['LON'][...].squeeze()[i-1,j-1],nc2['LON'][...].squeeze()[i+1,j+1],nc2['LON'][...].squeeze()[i-1,j+1],nc2['LON'][...].squeeze()[i+1,j-1])
                    #minlon=min(nc2['LON'][...].squeeze()[i-1,j-1],nc2['LON'][...].squeeze()[i+1,j+1],nc2['LON'][...].squeeze()[i-1,j+1],nc2['LON'][...].squeeze()[i+1,j-1])
                    #maxlat=max(nc2['LAT'][...].squeeze()[i-1,j-1],nc2['LAT'][...].squeeze()[i+1,j+1],nc2['LAT'][...].squeeze()[i-1,j+1],nc2['LAT'][...].squeeze()[i+1,j-1])
                    #minlat=min(nc2['LAT'][...].squeeze()[i-1,j-1],nc2['LAT'][...].squeeze()[i+1,j+1],nc2['LAT'][...].squeeze()[i-1,j+1],nc2['LAT'][...].squeeze()[i+1,j-1])
                   # print(nc2['LON'][...].squeeze()[i-1,j-1],nc2['LON'][...].squeeze()[i+1,j+1],nc2['LON'][...].squeeze()[i-1,j+1],nc2['LON'][...].squeeze()[i+1,j-1])    
                    #  cent_grdcell_x=nc2['LON'][...].squeeze()[i,j]
                #    print(nc2['LAT'][...].squeeze()[i-1,j-1],nc2['LAT'][...].squeeze()[i+1,j+1],nc2['LAT'][...].squeeze()[i-1,j+1],nc2['LAT'][...].squeeze()[i+1,j-1])
                #    print("----------------------------")
                    if(domain=='d04'):
                        deflat=0.0178
                        deflon=0.0229
                    elif(domain=='d01'):
                        deflat=0.45
                        deflon=0.65  
                    elif(domain=='d02'):
                        deflat=0.16
                        deflon=0.22     
                    elif(domain=='d03'):
                        deflat=0.053
                        deflon=0.071  
                    maxlon=nc2['LON'][...].squeeze()[i,j]+deflon
                    minlon=nc2['LON'][...].squeeze()[i,j]-deflon
                    maxlat=nc2['LAT'][...].squeeze()[i,j]+deflat
                    minlat=nc2['LAT'][...].squeeze()[i,j]-deflat  
                   # cent_grdcell_y=nc2['LAT'][...].squeeze()[i,j]
                #centre surronding
                    
                    #print(deflon,deflat)
                    if(deflon<0 or deflat<0):
                        print("xxxxxxx")
                    #print(cent_grdcell_y)
                  #  if((i<nc2['LON'][...].squeeze().shape[0]-1) & (j<nc2['LAT'][...].squeeze().shape[1])-1):
                  #      dlon=(nc2['LON'][...].squeeze()[i+1,j]-nc2['LON'][...].squeeze()[i,j])/2
                   #     dlat=-(nc2['LAT'][...].squeeze()[i,j+1]-nc2['LAT'][...].squeeze()[i,j])/2
                   # else:
                   #     dlon=(nc2['LON'][...].squeeze()[i,j]-nc2['LON'][...].squeeze()[i-1,j])/2
                   #     dlat=-(nc2['LAT'][...].squeeze()[i,j]-nc2['LAT'][...].squeeze()[i,j-1])/2
                   # if(dlat<0):
                   #     print(dlat)
                   # if(dlon<0):
                    #    print('kkkkk')
                    #Extend_i1_i1=np.array([cent_grdcell_x+dlon,cent_grdcell_y+dlat])
                    #Extend_i1_im1=np.array([cent_grdcell_x+dlon,cent_grdcell_y-dlat])
                    #Extend_im1_im1=np.array([cent_grdcell_x-dlon,cent_grdcell_y-dlat])
                    #Extend_im1_i1=np.array([cent_grdcell_x-dlon,cent_grdcell_y+dlat])
                   # if(Extend_im1_im1[0]>Extend_i1_i1[0]):
                   #     print('error lon')
                   # if(Extend_im1_im1[1]>Extend_i1_i1[1]):
                   #     print('error lat',dlat) 
                    #print(Extend_i1_i1,Extend_im1_im1)
                    #Area_grdcell[i,j]=arealatlon(minlat,minlon,maxlat,maxlon)
                    ind_lon=np.asarray(np.where((down_lon<=maxlon) &(down_lon>=minlon))).squeeze()
                    ind_lat=np.asarray(np.where((down_lat<=maxlat) & (down_lat>=minlat))).squeeze()

                    #print(nc['longitude'][...].min(),nc['longitude'][...].max(),nc['latitude'][...].min(),nc['latitude'][...].max())
                    #print(nc2['LON'][...].min(),nc2['LON'][...].max(),nc2['LAT'][...].min(),nc2['LAT'][...].max())
                   # print(ind_lon)
                   # print(ind_lat)
                    #print((ind_lat.size),(ind_lon.size))
                    #if((ind_lat.size==0) or (ind_lon.size==0)):
                      #  print('errr')
                   #     print(down_lon.max(),Extend_i1_i1[0],down_lon.min(),Extend_im1_im1[0])
                  #      print(down_lat.max(),Extend_i1_i1[1],down_lat.min(),Extend_im1_im1[1])
                    if((ind_lat.size>0) & (ind_lon.size>0)):
                        maxindlon=ind_lon.max()
                        minindlon=ind_lon.min()
                        maxindlat=ind_lat.max()
                        minindlat=ind_lat.min()
                        #print('hello')
                        unit_factor  =  (1000./16.)
                        #area_jooj=arealatlon(minlat,minlon,maxlat,maxlon)
                        emi_grdcell[i,j]=ch4_down[minindlat:maxindlat,minindlon:maxindlon].sum()*unit_factor
                        #if(emi_grdcell[i,j]>0):
                            #print(emi_grdcell[i,j])
                        month='May'
                        emisfolder ='/scratch/q90/sa6589/test_Sougol/run_cmaq/{}/{}'.format(yyyymmdd_dashed,domain)
                        grdem = Dataset('{}/Allmerged_emis_{}_{}.nc'.format(emisfolder,yyyymmdd_dashed,domain), 'w', format='NETCDF4_CLASSIC')    
                        lens = dict()
                        outdims = dict()
                        domShape = nc2['LAT'][...].squeeze().shape
                        
                        ## the main function in the script

 
                        #attributes that CMAQ is expecting(1)
                        attrnames = ['IOAPI_VERSION', 'EXEC_ID', 'FTYPE', 'CDATE', 'CTIME', 'WDATE', 'WTIME',
                                     'SDATE', 'STIME', 'TSTEP', 'NTHIK', 'NCOLS', 'NROWS', 'NLAYS', 'NVARS',
                                     'GDTYP', 'P_ALP', 'P_BET', 'P_GAM', 'XCENT', 'YCENT', 'XORIG', 'YORIG',
                                     'XCELL', 'YCELL', 'VGTYP', 'VGTOP', 'VGLVLS', 'GDNAM', 'UPNAM', 'VAR-LIST', 'FILEDESC']
                        unicodeType = type(u'foo')
                        for k in nc2.dimensions.keys():
                            lens[k] = len(nc2.dimensions[k])
                            ## get ready to write this to file
                        nlay = 1
                        nvar = 1
                        nz=1
                        lens['VAR'] = nvar
                        lens['LAY'] = nz
                        lens['TSTEP'] = 1
                        lens['DATE-TIME'] = 2

                        for k in lens.keys():
                            outdims[k] = grdem.createDimension(k, lens[k])
                        cmaqSpecList = ['CH4']
                        cmaqspec = 'CH4'
                        outvars = dict()
                        outvars['TFLAG'] = grdem.createVariable('TFLAG', 'i4', ('TSTEP','VAR','DATE-TIME',))
                        tflag = np.zeros(outvars['TFLAG'].shape, dtype=np.int32) #Peter
                        emisyear = date.timetuple().tm_year #Peter
                        #print(emisyear)
                        emisday=date.timetuple().tm_yday #Peter
                        outvars['TFLAG'].setncattr('long_name',"{:<16}".format('TFLAG'))
                        tflag[0,:,0] = 1000*emisyear+emisday #Peter
                        tflag[0,:,1] = 0 #means first minute of day #Peter
                        #print(emisday)
                        for iyyy in range(tflag.shape[1]):

                            #print(tflag)
                            outvars['TFLAG'][0,iyyy,0] = 1000*emisyear+emisday
                            outvars['TFLAG'][0,iyyy,1] = 0
                        ## one chunk per layer per time
                        outvars[cmaqspec] = grdem.createVariable(cmaqspec, 'f4', ('TSTEP', 'LAY', 'ROW', 'COL'), zlib = True, shuffle = False, chunksizes = np.array([1,1,domShape[0], domShape[1]]) )
                        outvars[cmaqspec].setncattr('long_name',"{:<16}".format(cmaqspec))
                        outvars[cmaqspec].setncattr('units',"{:<16}".format("mols/s"))
                        outvars[cmaqspec].setncattr('var_desc',"{:<80}".format("Emissions of " + cmaqspec))
                        outvars[cmaqspec][:] = np.float128(emi_grdcell)

                        for a in attrnames:
                            val = nc2.getncattr(a)
                            #print(a,val)
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

                            else:
                                grdem.setncattr(a,val)
                                
                            


                        #outvars['TFLAG'].setncattr('long_name',"{:<16}".format('TFLAG'))
                        #print(tflag)
                        #grdem.setncattr('TFLAG',tflag)
                        #print(grdem['TFLAG'][...][grdem['TFLAG'][...].mask == False])
                        #print(grdem['TFLAG'][...].data)
                        #VarString = "".join([ "{:<16}".format(k) for k in cmaqSpecList ])
                        #grdem.setncattr('VAR-LIST',VarString)
                        #grdem.setncattr('GDNAM',"{:<16}".format('Aus'))
                        #grdem.setncattr('NVARS',np.int32(len(emi_grdcell)))
                        grdem.setncattr('HISTORY',"")
                        #grdem.setncattr('SDATE',np.int32(-635))
                        #grdem.setncattr('TSTEP',numpy.int32(100))
                        grdem.close()



