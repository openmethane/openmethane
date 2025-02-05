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
    near_fields_array = np.array(near_fields)
    far_fields_array = np.array( far_fields)
    enhancement = near_fields_array -far_fields_array
    obs_baseline_mean_diff = enhancement[:,0,...].mean(axis=0)
    obs_baseline_std_diff = enhancement[:,0,...].std(axis=0)
    sim_baseline_mean_diff = enhancement[:,1,...].mean(axis=0)
    sim_baseline_std_diff = enhancement[:,1,...].std(axis=0)
    dss['obs_baseline_mean_diff'] = xr.DataArray(obs_baseline_mean_diff, dims=alerts_dims)
    dss['obs_baseline_std_diff'] = xr.DataArray(obs_baseline_std_diff, dims=alerts_dims)
    dss['sim_baseline_mean_diff'] = xr.DataArray(sim_baseline_mean_diff, dims=alerts_dims)
    dss['sim_baseline_std_diff'] = xr.DataArray(sim_baseline_std_diff, dims=alerts_dims)
    dss.to_netcdf(output_file)
    return

def create_alerts(
        baseline_file: pathlib.Path,
        daily_dir: pathlib.Path,
        obs_file_template: str = 'input/test_obs.pic.gz',
        sim_file_template: str = 'simulobs.pic.gz',
        output_file: str = 'alerts.nc',
        alerts_threshold: float = 0.0,
        significance_threshold: float = 1.0,
):
    '''
       constructs alerts.
       the baseline consists of a mean and standard deviation for local enhancement where the mean is based on simulations and the standard deviation on observations
       for the alert we consider whether the observed local enhancement lies outside the confidence interval defined by the mean and standard deviation and outside the confidence interval defined by the mean and threshold
       at each point in the domain.
       Output is stored as a netcdf file.
       It contains nans wherever an alert cannot be defined (usually no obs), 0 for no alert and 1 for an alert
       inputs:
       baseline_file: netcdf file describing the baseline (see function create_alerts_baseline. will be used to template the output.
       daily_dir: directory containing obs and simulation outputs as ObservationData.
       obs_file_template: string to be appended to  daily_dir to point to observations
       sim_file_template: string to be appended to daily_dir to point to simulations
       output_file: name of output_file, will be overwritten if exists
    '''
    near_threshold = float( os.getenv('ALERTS_NEAR_THRESHOLD', '0.2'))
    far_threshold = float( os.getenv('ALERTS_FAR_THRESHOLD', '1.0'))
    with xr.open_dataset( baseline_file) as ds:
        dss = ds.load()
        n_cols = dss.sizes['COL']
        n_rows = dss.sizes['ROW']
        lats = dss['LAT'].to_numpy().squeeze()
        lons = dss['LON'].to_numpy().squeeze()
        land_mask = dss['LANDMASK'].to_numpy().squeeze()
        baseline_mean = dss['sim_baseline_mean_diff'].to_numpy().squeeze()
        baseline_std = dss['obs_baseline_std_diff'].to_numpy().squeeze()
        alerts_dims = ('ROW', 'COL')
        ds.close()
    obs_list, sim_list = get_obs_sim(  daily_dir, obs_file_template, sim_file_template)
    obs_sim = [(o['latitude_center'], o['longitude_center'],\
                o['value'], s['value'],) for o,s in zip(obs_list, sim_list)]
    obs_sim_array = np.array( obs_sim)
    near, far = map_enhance(lats, lons, land_mask, obs_sim_array, near_threshold, far_threshold)
    enhancement = near -far
    obs_enhancement = enhancement[0,...]
    alerts = np.zeros( resultShape)
    alerts[...] = np.nan
    # first construct mask for points we cannot calcolate alert, either no baseline or no obs
    undefined_mask = np.isnan( obs_enhancement) | np.isnan( baseline_mean) | np.isnan( baseline_std)
    defined_mask = ~undefined_mask
    # now calculate alerts only where defined
    alerts[defined_mask] = float(
        ( np.abs( obs_enhancement - baseline_mean)[defined_mask] > significance_threshold *
          baseline_std[defined_mask]) &
        (np.abs( obs_enhancement -baseline_mean)[defined_mask] > alerts_threshold))

    dss['obs_enhancement'] = xr.DataArray(obs_enhacement, dims=alerts_dims)
    dss['alerts'] = xr.DataArray(alerts, dims=alerts_dims)
    dss.to_netcdf(output_file)
    return
def map_enhance(lat, lon, land_mask, concs, nearThreshold, farThreshold):
    nConcs = concs.shape[1]-2 # number of concentration records, the -2 removes lat,lon
    n_rows = land_mask.shape[0]
    n_cols = land_mask.shape[1]
    resultShape = (nConcs, n_rows, n_cols)
    near_field = np.zeros( resultShape)
    near_field[...] = np.nan
    far_field = np.zeros( resultShape)
    far_field[...] = np.nan
    # now build the input queue for multiprocessing points
    nCPUs = int(os.environ.get('NCPUS', '1'))
    input_proc_list = []
    for i,j in itertools.product(range(0,n_rows,1), range(0, n_cols,1)):
        if land_mask[ i,j] > 0.5: # land point
            input_proc_list.append(( i, j, lat, lon, land_mask, concs,\
                          nearThreshold, farThreshold))
    with multiprocessing.Pool( nCPUs) as pool:
        processOutput = pool.imap_unordered( point_enhance, input_proc_list)
        for obs in processOutput:
            i, j = obs[0:2]
            near_field[:, i, j], far_field[:, i, j] = obs[2:]
    return  near_field, far_field

def point_enhance( val):
    i, j, lat, lon, land_mask, concs, nearThreshold, farThreshold = val
    if land_mask[i,j] < 0.5: # ocean point
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
