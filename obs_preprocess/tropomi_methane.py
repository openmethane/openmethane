"""
oco2lite_preprocess.py

Copyright 2016 University of Melbourne.
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
"""



import glob
from netCDF4 import Dataset
import os
import pickle
import sys
import context
import time
from fourdvar.params.root_path_defn import store_path
import fourdvar.util.file_handle as fh
from model_space import ModelSpace
from obsTROPOMI_defn import ObsTROPOMI
import super_obs_util_peter as so_util

#-CONFIG-SETTINGS---------------------------------------------------------

#'filelist': source = list of OCO2-Lite files
#'directory': source = directory, use all files in source
#'pattern': source = file_pattern_string, use all files that match pattern
source_type = 'directory'

source = os.path.join( store_path, 'obs_TROPOMI_data' )
#source = os.path.join( store_path, 'obs_1day' )

output_file = './TROPOMI_observed.pic.gz'

#if true interpolate between 2 closest time-steps, else assign to closet time-step
interp_time = False

# variable to control thinning rate of observations for accelerated testing
thinningRate = 1 
#--------------------------------------------------------------------------

model_grid = ModelSpace.create_from_fourdvar()

if source_type.lower() == 'filelist':
    filelist = [ os.path.realpath( f ) for f in source ]
elif source_type.lower() == 'pattern':
    filelist = [ os.path.realpath( f ) for f in glob.glob( source ) ]
elif source_type.lower() == 'directory':
    dirname = os.path.realpath( source )
    filelist = [ os.path.join( dirname, f )
                 for f in os.listdir( dirname )
                 if os.path.isfile( os.path.join( dirname, f ) ) ]
else:
    raise TypeError( "source_type '{}' not supported".format(source_type) )
#organise variables by group 
instrument_var = [ 'pixel_id',
             'latitude_corners',
                   'longitude_corners',
             'latitude_center',
             'longitude_center',
             'time',
             'solar_zenith_angle',
             'viewing_zenith_angle',
             'solar_azimuth_angle',
             'viewing_azimuth_angle']
target_var = ['co_column',
             'co_column_precision',
             'co_profile_apriori',
              'co_column_apriori',
             #'pressure_levels',
             'co_column_averaging_kernel']
meteo_var = ['landflag', 'pressure_levels']
diagnostics_var = ['processing_quality_flags', 'qa_value']


obslist = []
for fname in filelist:
    print('read {}'.format( fname ))
    var_dict = {}
    with Dataset( fname, 'r' ) as f:
        size = f.dimensions[ 'nobs' ].size
        for var in instrument_var:
            var_dict[ var ] = f.groups['instrument'].variables[ var ][:]
        for var in target_var:
            var_dict[ var ] = f.groups['target_product'].variables[ var ][:]
        #for var in sounding_var:
        #    var_dict[ var ] = f.groups[ 'Sounding' ].variables[ var ][:]
        for var in meteo_var:
            var_dict[ var ] = f.groups[ 'meteo' ].variables[ var ][:]
        for var in diagnostics_var:
            var_dict[ var ] = f.groups[ 'diagnostics' ].variables[ var ][:]

    print('found {} soundings'.format( size ))
    # squeeze down multiple dimensions
    for k in var_dict.keys(): var_dict[k] = var_dict[k].squeeze()
    print('time after reading',fname,time.process_time())
    sounding_list = []
    for i in range(0, size, thinningRate ):
# a series of tests, any of which will rule out the sounding
        if so_util.max_quality_only is True and var_dict['processing_quality_flags'][i] != 0: continue
        if so_util.surface_type != -1 and var_dict['landflag'][i] != so_util.surface_type: continue
        if so_util.operation_mode != -1 and var_dict['operation_mode'][i] != so_util.operation_mode: continue
        lat = var_dict['latitude_center'][i]
        lon = var_dict['longitude_center'][i]
        if not model_grid.lat_lon_inside( lat=lat, lon=lon ): continue
        # made it through tests now append to list
        src_dict = { k: v[i] for k,v in var_dict.items() }
        if so_util.group_by_second is True: src_dict['sec'] = int( src_dict['time'][0])
        sounding_list.append( src_dict )


    if so_util.group_by_second is True:
        sec_list = list( set( [ s['sec'] for s in sounding_list ] ) )
        merge_list = []
        for sec in sec_list:
            sounding = so_util.merge_second( [ s
                       for s in sounding_list if s['sec'] == sec ] )
            merge_list.append( sounding )
        sounding_list = merge_list
    print("obs converted from 2018 to 2019")
    for sounding in sounding_list:
        sounding['time'][0] = 2019
        obs = ObsTROPOMI.create( **sounding )
        obs.interp_time = interp_time
        obs.model_process( model_grid )
       # print(sounding)
        if obs.valid is True:
            obslist.append( obs.get_obsdict() ) 
    print('time after processing ',fname,time.process_time())

    
if so_util.group_by_column is True:
    obslist = [ o for o in obslist if so_util.is_single_column(o) ]
    col_list = list( set( [ so_util.get_col_id(o) for o in obslist ] ) )
    merge_list = []
    for col in col_list:
        obs = so_util.merge_column( [ o for o in obslist
                                      if so_util.get_col_id(o) == col ] )
        merge_list.append( obs )
    obslist = merge_list
#with open('soundings_all.pkl', 'wb') as f:
#        pickle.dump(sounding_list, f)   
#print(len(obs_list))
print('time after merging ',time.process_time())
if len( obslist ) > 0:
    domain = model_grid.get_domain()
    datalist = [ domain ] + obslist
    fh.save_list( datalist, output_file )
    print('recorded observations to {}'.format( output_file ))
else:
    print('No valid observations found, no output file generated.')
