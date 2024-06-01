"""
obsOCO2_defn.py

Copyright 2016 University of Melbourne.
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
"""

import numpy as np
import datetime as dt
from obs_preprocess.ray_trace import Ray
from obs_preprocess.obs_defn import ObsMultiRay

class ObsOCO2( ObsMultiRay ):
    """Single observation (or sounding) from OCO2 satellite
    This observation class only works for 1 species.
    """
    required = ['value','uncertainty','weight_grid','offset_term']
    
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
        newobs = cls( obstype='OCO2_sounding' )
        newobs.out_dict['value'] = kwargs['xco2']
        newobs.out_dict['uncertainty'] = kwargs['xco2_uncertainty']

        # newobs.out_dict['OCO2_id'] = kwargs['sounding_id']
        #newobs.out_dict['surface_type'] = kwargs['surface_type']
        #newobs.out_dict['operation_mode'] = kwargs['operation_mode']
        #OCO2 Lite-files only record CO2 values
        newobs.spcs = 'CO2'
        newobs.src_data = kwargs.copy()
        return newobs
    
    def model_process( self, model_space ):
        ObsMultiRay.model_process( self, model_space )
        #set lite_coord to surface cell with largest weight
        if 'weight_grid' in self.out_dict.keys():
            surf = [ (v,k) for k,v in self.out_dict['weight_grid'].items()
                     if k[2]==0 ]
            self.out_dict[ 'lite_coord' ] = max(surf)[1]
        return None
    
    def add_visibility( self, proportion, model_space ):
        #obs pressure is in hPa, convert to model units (Pa)
        obs_pressure = 100. * np.array( self.src_data[ 'pressure_levels' ] )
        obs_kernel = np.array( self.src_data[ 'xco2_averaging_kernel' ] )
        obs_apriori = np.array( self.src_data[ 'co2_profile_apriori' ] )
        
        #get sample model coordinate at surface
        coord = [ c for c in proportion.keys() if c[2] == 0 ][0]
        
        model_pweight = model_space.get_pressure_weight( coord )
        model_kernel = model_space.pressure_interp( obs_pressure, obs_kernel, coord )
        model_apriori = model_space.pressure_interp( obs_pressure, obs_apriori, coord )
        
        model_vis = model_pweight * model_kernel
        column_xco2 = ( model_pweight * model_kernel * model_apriori )
        self.out_dict['offset_term'] = self.src_data['xco2_apriori'] - column_xco2.sum()
        
        weight_grid = {}
        for l, weight in enumerate( model_vis ):
            layer_slice = { c:v for c,v in proportion.items() if c[2] == l }
            layer_sum = sum( layer_slice.values() )
            weight_slice = { c: weight*v/layer_sum for c,v in layer_slice.items() }
            weight_grid.update( weight_slice )
        
        return weight_grid
    
    def map_location( self, model_space ):
        assert model_space.gridmeta['GDTYP'] == 2, 'invalid GDTYP'
        #convert source location data into a list of spacial points
        lat = self.src_data[ 'latitude' ]
        lon = self.src_data[ 'longitude' ]
        p0_zenith = np.radians( self.src_data[ 'solar_zenith_angle' ] )
        p0_azimuth = np.radians( self.src_data[ 'solar_azimuth_angle' ] )
        p2_zenith = np.radians( self.src_data[ 'sensor_zenith_angle' ] )
        p2_azimuth = np.radians( self.src_data[ 'sensor_azimuth_angle' ] )
        
        x1,y1 = model_space.get_xy( lat, lon )
        p1 = (x1,y1,0)
        p0 = model_space.get_ray_top( p1, p0_zenith, p0_azimuth )
        p2 = model_space.get_ray_top( p1, p2_zenith, p2_azimuth )
        
        ray_in = Ray( p0, p1 )
        ray_out = Ray( p1, p2 )
        try:
            in_dict = model_space.grid.get_ray_cell_dist( ray_in )
            out_dict = model_space.grid.get_ray_cell_dist( ray_out )
        except AssertionError:
            self.coord_fail( 'outside grid area' )
            return None
        
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
        fulltime = dt.datetime.utcfromtimestamp( self.src_data[ 'time' ] )
        day = int( fulltime.strftime( '%Y%m%d' ) )
        time = int( fulltime.strftime( '%H%M%S' ) )
        self.time = [ day, time ]
        #use generalized function
        return ObsMultiRay.map_time( self, model_space )
