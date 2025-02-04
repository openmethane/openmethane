#
# Copyright 2025 The Superpower Institute Ltd
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

import os
import typing
import numpy as np
import glob
import pathlib
import pickle
import gzip
import itertools
import multiprocessing

import xarray as xr

ALERTS_MINIMUM_DATA = 1 # nimimum data required to define alerts baseline

def iterPickle(filename, compressed=True):
    with gzip.open(filename) if compressed else open(filename, 'rb') as f:
        while True:
            try:
                yield pickle.load(f)
            except EOFError:
                break

def read_obs_file( path:  pathlib.Path,
                   pop_keys: list =None,) -> list:
    ''' read obs from file
    remove keys specified by pop_keys if present.'''
    result = [_ for _ in iterPickle( path)]
    # throw away domain spec as first element
    result.pop(0)
    if pop_keys is not None:
        for b in result:
            for k in pop_keys:
                b.pop(k)
    return result

def get_obs_sim(
        dir: pathlib.Path | str,
        obs_file_template: str,
        sim_file_template: str,
        ):
    '''
       reads obs and simulations from dir/obs_template_file and dir/sim_template_file,
       checks for consistency of coordinates
'''
    obs_path = pathlib.Path.joinpath( pathlib.Path(dir), obs_file_template)
    obs_list = read_obs_file( obs_path, pop_keys=['weight_grid'])
    sim_path = pathlib.Path.joinpath( pathlib.Path(dir), sim_file_template)
    sim_list = read_obs_file( sim_path, pop_keys=['weight_grid'])
    if len(sim_list) != len( obs_list):
        raise ValueError('inconsistent lenghts for obs and sim')
    for obs, sim in zip( obs_list, sim_list):
        if obs['lite_coord'] != sim['lite_coord']:
            raise ValueError('inconsistent lite coord')
    return obs_list, sim_list
        
def create_alerts_baseline(
        domain_file: pathlib.Path,
        dir_list: typing.Iterable,
        obs_file_template: str = 'input/test_obs.pic.gz',
        sim_file_template: str = 'simulobs.pic.gz',
        output_file: str = 'alerts_baseline.nc',
        ):
    '''constructs a baseline for alerts.
       the baseline consists of a mean and standard deviation for the differences between obs and simulation
       at each point in the domain.
       Output is stored as a netcdf file.
       inputs:
       domain_file: netcdf file describing the domain, will be used to template the output.
       dir_list: list of directories containing obs and simulation outputs as ObservationData.
       obs_file_template: string to be appended to each dir in dir_list to point to observations
       sim_file_template: string to be appended to each dir in dir_list to point to simulations
       output_file: name of output_file, will be overwritten if exists
    '''
    near_threshold = float( os.getenv('ALERTS_NEAR_THRESHOLD', '0.2'))
    far_threshold = float( os.getenv('ALERTS_FAR_THRESHOLD', '1.0'))
    with xr.open_dataset( domain_file) as ds:
        dss = ds.load()
        n_cols = dss.sizes['COL']
        n_rows = dss.sizes['ROW']
        lats = dss['LAT'].to_numpy().squeeze()
        lons = dss['LON'].to_numpy().squeeze()
        land_mask = dss['LANDMASK'].to_numpy().squeeze()
        alerts_dims = ('ROW', 'COL')
    near_fields = []
    far_fields = []
    for dir in dir_list:
        obs_list, sim_list = get_obs_sim(  dir, obs_file_template, sim_file_template)
        obs_sim = [(o['latitude_center'], o['longitude_center'],\
                    o['value'], s['value'],) for o,s in zip(obs_list, sim_list)]
        obs_sim_array = np.array( obs_sim)
        near, far = map_enhance(lats, lons, land_mask, obs_sim_array, near_threshold, far_threshold)
        near_fields.append( near)
        far_fields.append( far)
    dss['baseline_mean_diff'] = xr.DataArray(baseline_mean_diff, dims=alerts_dims)
    dss['baseline_std_diff'] = xr.DataArray(baseline_std_diff, dims=alerts_dims)
    dss.to_netcdf(output_file)
    return

def map_enhance( emis, lat, lon, landMask, concs, nearThreshold, farThreshold):
    nConcs = concs.shape[1]-3 # number of concentration records, the -3 removes lat,lon,time
    resultShape = (nConcs,)+land_mask.shape
    near_field = np.zeros( resultShape)
    far_field = np.zeros( resultShape)
    # now build the input queue for multiprocessing points
    nCPUs = int(os.environ.get('NCPUS', '1'))
    input_proc_list = []
    for i,j in itertools.product(range(0,emis.shape[0],100), range(0, emis.shape[1],100)):
        if landMask[ i,j] > 0.5: # land point
            input_proc_list.append(( i, j, lat, lon, landMask, concs,\
                          nearThreshold, farThreshold))
    with multiprocessing.Pool( nCPUs) as pool:
        processOutput = pool.imap_unordered( point_enhance, input_proc_list)
        for obs in processOutput:
            i, j = obs[0:2]
            near_field[:, i, j], far_field[:, i, j] = obs[2:]
    return  near_field, far_field

def point_enhance( val):
    i, j, lat, lon, landMask, concs, nearThreshold, farThreshold = val
    if landMask[i,j] < 0.5: # ocean point
        return i,j,0.,0.
    else:
        dist = calc_dist( concs, (lat[i,j], lon[i,j]))
        near = dist < nearThreshold
        far = (dist > nearThreshold ) & (dist < farThreshold)
        nearCount = near.sum()
        farCount = far.sum()
        if ( nearCount == 0) or (farCount == 0):
            return i,j,0.,0.
        else:
            near_field = concs[near,2:].mean( axis=0)
            far_field = concs[far,2:].mean( axis=0)
            return i,j, near_field, far_field


def calc_dist( concs, loc):
    diff = concs[:, 0:2] -np.array(loc)
    dist = (diff[:,0]**2 + diff[:,1]**2)**0.5
    return dist
