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

import datetime as dt
import numpy as np

from obs_preprocess.obs_defn import ObsMultiRay
from obs_preprocess.ray_trace import Point, Ray

#physical constants
grav = 9.807
mwair = 28.9628
avo = 6.022e23
kg_scale = 1000.
cm_scale = 100.*100.
ppm_scale = 1000000.
class ObsTROPOMI( ObsMultiRay ):
    """Single observation  from TROPOMI 
    This observation class only works for 1 species.
    """
    required = ['value','uncertainty','weight_grid','offset_term']
    default = {'lite_coord':None}
    @classmethod
    def create( cls, **kwargs ):
        """kwargs comes from variables in oco2 file.
        min. requirements for kwargs:
        - sounding_id : long_int
        - latitude : float (degrees)
        - longitude : float (degrees)
        - time : float (unix timestamp)
        - solar_zenith_angle : float (degrees)
        - sensor_zenith_angle : float (degrees)
        - solar_azimuth_angle : float (degrees)
        - sensor_azimuth_angle : float (degrees)
        - warn_level : byte_int
        - xco2 : float (ppm)
        - xco2_uncertainty : float (ppm)
        - xco2_apriori : float (ppm)
        - co2_profile_apriori : array[ float ] (length=levels, units=ppm)
        - xco2_averaging_kernel : array[ float ] (length=levels)
        - pressure_levels : array[ float ] (length=levels, units=hPa)
        - pressure_weight : array[ float ] (length=levels)
        """
        newobs = cls( obstype='TROPOMI_sounding' )
       # newobs.out_dict['value'] = kwargs['co_column']
        newobs.out_dict['uncertainty'] = kwargs['co_column_precision']
        
        # newobs.out_dict['OCO2_id'] = kwargs['sounding_id']
        #newobs.out_dict['surface_type'] = kwargs['surface_type']
        newobs.out_dict['surface_type'] = kwargs['landflag']
       # newobs.out_dict['operation_mode'] = kwargs['operation_mode']
        newobs.out_dict['processing_quality_flags'] = kwargs['processing_quality_flags']
        newobs.out_dict['co_profile_apriori'] = kwargs['co_profile_apriori']
        sron_alpha = kwargs['co_column'] / kwargs['co_column_apriori']
        newobs.out_dict['value'] = sron_alpha
        #OCO2 Lite-files only record CO2 values
        newobs.spcs = 'CO'
        newobs.src_data = kwargs.copy()
        return newobs
    def _convert_ppm( self, value, pressure_interval ):
        """convert molec. cm-2 to ppm"""
        ppm_value = ( ppm_scale * (value * cm_scale / avo) /
                      ( pressure_interval * kg_scale / (grav * mwair) ) )
        return ppm_value
    
    def model_process( self, model_space ):
        ObsMultiRay.model_process( self, model_space )
        #now created self.out_dict[ 'weight_grid' ]
        if 'weight_grid' in self.out_dict.keys():
            day,time,_,_,_,spc = list(self.out_dict['weight_grid'].keys())[0]
            x,y = model_space.get_xy( self.src_data['latitude_center'],
                                      self.src_data['longitude_center'] )
            col,row,lay = model_space.grid.get_cell( Point((x,y,0)) )
            self.out_dict[ 'lite_coord' ] = (day,time,lay,row,col,spc,)

        return None
    
    def add_visibility( self, proportion, model_space ):
        #obs pressure is in Pa,  model units Pa (unlike oco)
        obs_pressure_bounds = np.array( self.src_data[ 'pressure_levels' ] )
        obs_pressure_center = 0.5 * ( obs_pressure_bounds[1:] + obs_pressure_bounds[:-1] )
        obs_p_bound =  np.array( self.src_data[ 'pressure_levels' ] )
        obs_pressure = 0.5 * (obs_p_bound[:-1]+obs_p_bound[1:])
        obs_pressure_interval = ( obs_pressure_bounds[1:] - obs_pressure_bounds[:-1] )
        sron_unc_molec = self.src_data['co_column_precision']
        sron_unc_ppm_orig = self._convert_ppm( sron_unc_molec, obs_pressure_interval.sum() )
        sron_unc_ppm_new  = 0.009 ##constant obs_unc
       #not same thing as kernel
        obs_kernel = np.array( self.src_data[ 'co_column_averaging_kernel' ] ) 
        obs_apriori = np.array( self.src_data[ 'co_profile_apriori' ] )
       # newobs.out_dict['uncertainty'] = in ppm UPDATE HERE
        #get sample model coordinate at surface
        coord = [ c for c in proportion.keys() if c[2] == 0 ][0]
        model_pweight = model_space.get_pressure_weight( coord )
        ref_profile_molec = self.src_data['co_profile_apriori']
       # ref_profile_mol = ref_profile_molec / avo
        ref_profile_ppm = self._convert_ppm( ref_profile_molec, obs_pressure_interval )
        model_ref_profile = model_space.pressure_interp( obs_pressure_center,
                                                         ref_profile_ppm, coord )
        model_kernel = model_space.pressure_interp( obs_pressure, obs_kernel, coord )
        model_apriori = model_space.pressure_interp( obs_pressure, obs_apriori, coord )
        model_unc_orig = sron_unc_ppm_orig / ((model_pweight*model_ref_profile)).sum()
        model_unc_new  = sron_unc_ppm_new / ((model_pweight*model_ref_profile)).sum()
        self.out_dict['uncertainty']       = model_unc_new ##this is the parameter that is used for the next process
        self.out_dict['uncertainty_orig']  = model_unc_orig
        self.out_dict['uncertainty_new']   = model_unc_new     ##
        self.out_dict['sron_unc_ppm_orig'] = sron_unc_ppm_orig ##
        self.out_dict['sron_unc_ppm_new']  = sron_unc_ppm_new  ##
        self.out_dict['ref_profile'] = model_ref_profile
 
        model_vis = model_pweight * model_kernel
        column_xco = ( model_pweight * model_kernel * model_apriori )
        self.out_dict['offset_term'] = self.src_data['co_profile_apriori'] - column_xco.sum()
        
        weight_grid = {}
        for l, weight in enumerate( model_vis ):
           # lrtainty : float (ppm)
           # co_column_apriori : float (ppm)
           # co_column_apriori : array[ float ] (length=levels, units=ppm)
           # co_column_averaging_kernel : array[ float ] (length=levels)
           # pressure_levels : array[ float ] (length=levels, units=hPa)
           # pressure_weight : array[ float ] (length=levels)
        
    
            layer_slice = { c:v for c,v in proportion.items() if c[2] == l }
            layer_sum = sum( layer_slice.values() )
            weight_slice = { c: weight*v/layer_sum for c,v in layer_slice.items() }
            weight_grid.update( weight_slice )
        
      #  a_scale = 0
      #  for coord, weight in weight_grid.items():
      #      lay = coord[2]
      #      a_scale += (weight*model_ref_profile[lay])**2
      #  self.out_dict['alpha_scale'] = a_scale

        return weight_grid
      
    def map_location( self, model_space ):
        assert model_space.gridmeta['GDTYP'] == 2, 'invalid GDTYP'
        #convert source location data into a list of spacial points
        #print("this is actually being called but just checking")
        lat = self.src_data[ 'latitude_center' ]
        lon = self.src_data[ 'longitude_center' ]
        p0_zenith = np.radians( self.src_data[ 'solar_zenith_angle' ] )
        p0_azimuth = np.radians ( self.src_data[ 'solar_azimuth_angle' ] ) 
        p2_zenith = np.radians( self.src_data[ 'viewing_zenith_angle' ] )
        p2_azimuth = np.radians( self.src_data[ 'viewing_azimuth_angle' ] )
       # print( lat, lon )
        x1,y1 = model_space.get_xy( lat, lon )
       # print("x y",  model_space.proj( 134, -30 ))
      #  print("lon, lat" , model_space.proj(x1, y1 , inverse=True ))
        p1 = (x1,y1,0)
        p0 = model_space.get_ray_top( p1, p0_zenith, p0_azimuth )
        p2 = model_space.get_ray_top( p1, p2_zenith, p2_azimuth )
        ray_in = Ray( p0, p1 )
        ray_out = Ray( p1, p2 )
       # print(p0, p1, p2)
       # print(model_space.grid.edges)
        try:
            in_dict = model_space.grid.get_ray_cell_dist( ray_in )
            out_dict = model_space.grid.get_ray_cell_dist( ray_out )
          #  print(out_dict)       
        except AssertionError:
           # print( 'we missed')
       # raise(ValueError)
            self.coord_fail( 'outside grid area' )

            return None
       # print(out_dict, "out dict", len(out_dict)) 
        dist_dict = in_dict.copy()
        for coord, val in out_dict.items():
            dist_dict[ coord ] = dist_dict.get( coord, 0 ) + val
        tdist = sum( dist_dict.values() )
            
        #convert x-y-z into lay-row-col and scale values so they sum to 1
        result = { (lay,row,col):val/tdist for [(col,row,lay,),val]
                   in dist_dict.items() if val > 0.0 }
        return result
    
    def map_time( self, model_space ):
        #convert source time into [ int(YYYYMMDD), int(HHMMSS) ]
       # fulltime = dt.datetime.utcfromtimestamp( self.src_data[ 'time' ])
        t_array = self.src_data[ 'time' ]
        fulltime = dt.datetime(year = t_array[0], month = t_array[1], day = t_array[2], hour = t_array[3], minute = t_array[4], second = t_array[5])
       # print('time called')
        day = int( fulltime.strftime( '%Y%m%d' ) )
        time = int( fulltime.strftime( '%H%M%S' ) )
        self.time = [ day, time ]
       # print(self.time) 
        #use generalized function
        return ObsMultiRay.map_time( self, model_space )
    
