"""
obsSRON_defn.py

Copyright 2016 University of Melbourne.
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
"""

import numpy as np
import datetime as dt
from ray_trace import Point, Ray
from obs_defn import ObsMultiRay
##NS added:
import pdb

#physical constants
grav = 9.807
mwair = 28.9628
avo = 6.022e23
kg_scale = 1000.
cm_scale = 100.*100.
ppm_scale = 1000000.

class ObsSRON( ObsMultiRay ):
    """Single observation of CH4 from TROPOMI instrument, processed by ESA
    This observation class only works for 1 species.
    """
    required = ['value','uncertainty','weight_grid','alpha_scale'] 
    #remove offset_term from default dict for obs.
    default = {'lite_coord':None}
    
    @classmethod
    def create( cls, **kwargs ):
        """kwargs comes from variables in S5P file.
        min. requirements for kwargs:
        - time : datetime-obj (datetime)
        - latitude_center : float (degrees)
        - longitude_center : float (degrees)
        - latitude_corners : array[ float ] (length=4, units=degrees)
        - longitude_corners : array[ float ] (length=4, units=degrees)
        - solar_zenith_angle : float (degrees)
        - viewing_zenith_angle : float (degrees)
        - solar_azimuth_angle : float (degrees)
        - viewing_azimuth_angle : float (degrees)
        - pressure_levels : array[ float ] (length=levels, units=Pa)
        - co_column : float (molec. cm-2)
        - co_column_precision : float (molec. cm-2)
        - co_column_apriori : float (molec. cm-2)
        - co_profile_apriori : array[ float ] (length=levels, units=molec. cm-2)
        - qa_value : float (unitless)
        """
        newobs = cls( obstype='ESA_co_obs' )
        
        newobs.out_dict['value'] = kwargs['ch4_column']
        newobs.out_dict['uncertainty'] = kwargs['ch4_column_precision']
        newobs.out_dict['time'] = kwargs['time']
        newobs.out_dict['qa_value'] = kwargs['qa_value']
        newobs.out_dict['latitude_corners'] = kwargs['latitude_corners']
        newobs.out_dict['longitude_corners'] = kwargs['longitude_corners']
        newobs.out_dict['latitude_center'] = kwargs['latitude_center']
        newobs.out_dict['longitude_center'] = kwargs['longitude_center']
        newobs.spcs = 'CH4'
        newobs.src_data = kwargs.copy()
        return newobs
    
    def _convert_ppm( self, value, pressure_interval ):
        """convert mole m-2 to ppm"""
        ppm_value =  value / (( pressure_interval * kg_scale) / (grav * mwair * ppm_scale)) 
        return ppm_value
    
    def model_process( self, model_space ):
        ObsMultiRay.model_process( self, model_space )
        #set lite_coord to surface cell containing lat/lon center
        if 'weight_grid' in list(self.out_dict.keys()):
            day,time,_,_,_,spc = list(self.out_dict['weight_grid'].keys())[0]
            x,y = model_space.get_xy( self.src_data['latitude_center'],
                                      self.src_data['longitude_center'] )
            col,row,lay = model_space.grid.get_cell( Point((x,y,0)) )
            self.out_dict[ 'lite_coord' ] = (day,time,lay,row,col,spc,)
            self.ready = True
        return None
    
    def add_visibility( self, proportion, model_space ):
        obs_pressure_bounds = np.array( self.src_data[ 'pressure_levels' ] )
        obs_pressure_center = 0.5 * ( obs_pressure_bounds[1:] + obs_pressure_bounds[:-1] )
        obs_pressure_interval = ( obs_pressure_bounds[1:] - obs_pressure_bounds[:-1] )
        ESA_unc_molec = self.src_data['ch4_column_precision']
        ESA_unc_ppm  = 0.009 ##I set this value to test how the magnitude of unc can effect the cost-functions/gradients  
        
        #get sample model coordinate at surface
        coord = [ c for c in list(proportion.keys()) if c[2] == 0 ][0]

        #need to save the ref. profile concentration & obs. uncertainty.
        model_pweight = model_space.get_pressure_weight( coord )
        ref_profile_mole = self.src_data['ch4_profile_apriori'] 
        ref_profile_ppm = self._convert_ppm( ref_profile_mole, obs_pressure_interval )
        model_ref_profile = model_space.pressure_interp( obs_pressure_center,
                                                         ref_profile_ppm, coord )
        model_unc  = 20. # arbitrary constant unc in ppb
        self.out_dict['uncertainty']       = model_unc ##this is the parameter that is used for the next process
        self.out_dict['ref_profile'] = model_ref_profile
        self.out_dict['model_pweight'] = model_pweight
        self.out_dict['obs_kernel'] = self.src_data['obs_kernel']
        
        #ref profile used in obs_operator & alpha_scale, not here.
        model_vis = model_pweight# * model_ref_profile
        self.out_dict['model_vis'] = model_vis
        
        weight_grid = {}
        for l, weight in enumerate( model_vis ):
            layer_slice = { c:v for c,v in list(proportion.items()) if c[2] == l }
            layer_sum = sum( layer_slice.values() )
            weight_slice = { c: weight*v/layer_sum for c,v in list(layer_slice.items()) }
            weight_grid.update( weight_slice )
        
        # alpha-scale denominator must use the same weight-grid as the obs-op
        a_scale = 0
        for coord, weight in list(weight_grid.items()):
            lay = coord[2]
            a_scale += (weight*model_ref_profile[lay])**2
        self.out_dict['alpha_scale'] = a_scale
        self.out_dict['weight_grid'] = weight_grid
        
        return weight_grid
    
    def map_location( self, model_space ):
        assert model_space.gridmeta['GDTYP'] == 2, 'invalid GDTYP'
        #convert source location data into a list of spacial points
        lat_list = self.src_data[ 'latitude_corners' ]
        lon_list = self.src_data[ 'longitude_corners' ]
        p0_zenith = np.radians( self.src_data[ 'solar_zenith_angle' ] )
        p0_azimuth = np.radians( self.src_data[ 'solar_azimuth_angle' ] )
        if p0_azimuth < 0.: p0_azimuth += 2*np.pi
        p2_zenith = np.radians( self.src_data[ 'viewing_zenith_angle' ] )
        p2_azimuth = np.radians( self.src_data[ 'viewing_azimuth_angle' ] )
        if p2_azimuth < 0.: p2_azimuth += 2*np.pi

        rays_in = []
        rays_out = []    
        ###pdb.set_trace()    
        for lat,lon in zip( lat_list, lon_list ):
            x1,y1 = model_space.get_xy( lat, lon )
            p1 = (x1,y1,0,)
            p0 = model_space.get_ray_top( p1, p0_zenith, p0_azimuth )
            p2 = model_space.get_ray_top( p1, p2_zenith, p2_azimuth )
            rays_in.append( Ray( p1, p0 ) )
            rays_out.append( Ray( p1, p2 ) )

        try:
            in_dict = model_space.grid.get_beam_intersection_volume( rays_in )
            out_dict = model_space.grid.get_beam_intersection_volume( rays_out )
        except AssertionError:
            self.coord_fail( 'outside grid area' )
            return None
        
        area_dict = in_dict.copy()
        for coord, val in list(out_dict.items()):
            area_dict[ coord ] = area_dict.get( coord, 0 ) + val
        tarea = sum( area_dict.values() )
            
        #convert x-y-z into lay-row-col and scale values so they sum to 1
        result = { (lay,row,col):val/tarea for [(col,row,lay,),val]
                   in list(area_dict.items()) if val > 0. }
        return result
    
    def map_time( self, model_space ):
        #convert source time into [ int(YYYYMMDD), int(HHMMSS) ]
        fulltime = self.src_data[ 'time' ]
        day = int( fulltime.strftime( '%Y%m%d' ) )
        time = int( fulltime.strftime( '%H%M%S' ) )
        self.time = [ day, time ]
        #use generalized function
        return ObsMultiRay.map_time( self, model_space )
