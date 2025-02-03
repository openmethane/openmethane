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

def append_obs_sim(
        obs_sim_lists: np.array,
        dir: pathlib.Path | str,
        obs_file_template: str,
        sim_file_template: str,
        ):
    '''
       reads obs and simulations from dir/obs_template_file and dir/sim_template_file
       and appends the value field from each attached to the i,j coordinate from lite_coord.
       Checks that the lite_coord is consistent between obs and sim.
       Appending happens to obs_sim_lists which is a 2d array of lists.
       appending is in place so nothing is returned.
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
        ind = obs['lite_coord'][3:5]
        obs_sim_lists[ind].append((obs['value'], sim['value']))

        
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
    # first create 2d array of lists of paired obs and simulations, start with empty lists
    with xr.open_dataset( domain_file) as ds:
        dss = ds.load()
        n_cols = dss.sizes['COL']
        n_rows = dss.sizes['ROW']
        alerts_dims = ('ROW', 'COL')
    obs_sim_lists = np.empty((n_rows, n_cols), dtype=object)
    for j,i in  itertools.product(range( n_rows), range( n_cols)):
        obs_sim_lists[j,i] = []
    # now add observation-simulation pairs from each run to their relevant points
    for dir in dir_list:
        append_obs_sim( obs_sim_lists, dir, obs_file_template, sim_file_template)
    baseline_mean_diff = np.zeros_like( obs_sim_lists)
    baseline_std_diff = np.zeros_like( obs_sim_lists)
    for j,i in  itertools.product(range( n_rows), range( n_cols)):
        if len( obs_sim_lists[j,i]) <= ALERTS_MINIMUM_DATA: # not enough obs here for obs and std-dev
            baseline_mean_diff[j,i] = np.nan
            baseline_std_diff[j,i] = np.nan
        else:
            paired_array = np.array( obs_sim_lists[j,i])
            baseline_mean_diff[j,i] = (paired_array[:,0] -paired_array[:,1]).mean()
            baseline_std_diff[j,i] = (paired_array[:,0] -paired_array[:,1]).std()
    dss['baseline_mean_diff'] = xr.DataArray(baseline_mean_diff, dims=alerts_dims)
    dss['baseline_std_diff'] = xr.DataArray(baseline_std_diff, dims=alerts_dims)
    dss.to_netcdf(output_file)
    return

