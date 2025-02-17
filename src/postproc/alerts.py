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
import datetime
import os
import numpy as np
import logging
import pathlib
import pickle
import gzip
import itertools
import multiprocessing

import xarray as xr

from util.netcdf import extract_bounds

ALERTS_MINIMUM_DATA = 1 # nimimum data required to define alerts baseline

logger = logging.getLogger(__name__)

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
    logger.debug(f"Loading observation data from {dir}")

    obs_path = pathlib.Path.joinpath( pathlib.Path(dir), obs_file_template)
    obs_list = read_obs_file( obs_path, pop_keys=['weight_grid'])
    sim_path = pathlib.Path.joinpath( pathlib.Path(dir), sim_file_template)
    sim_list = read_obs_file( sim_path, pop_keys=['weight_grid'])
    if len(sim_list) != len( obs_list):
        raise ValueError('inconsistent lenghts for obs and sim')

    period_start: datetime.datetime | None = None
    period_end: datetime.datetime | None = None

    for obs, sim in zip( obs_list, sim_list):
        if (period_start is None) or (period_start > obs['time']):
            period_start = obs['time']
        if (period_end is None) or (period_end < obs['time']):
            period_end = obs['time']
        if obs['lite_coord'] != sim['lite_coord']:
            raise ValueError('inconsistent lite coord')
    return obs_list, sim_list, period_start, period_end

def calculate_baseline_statistics( near_fields_array: np.ndarray,
                                   far_fields_array: np.ndarray,
                                   ) -> tuple[ np.ndarray]:
    """ calculates baseline statistics of mean and standard deviation of
       local enhancement along with number of valid samples for each spatial point.
    """
    logger.info('calculating baseline statistics')
    # enforce types
    near_fields_array = np.array( near_fields_array)
    far_fields_array = np.array(far_fields_array)
    # check consistent masking
    if (np.isnan( near_fields_array) != np.isnan( far_fields_array)).any():
        raise ValueError("inconsistent masking of near and far fields")
    baseline_count = (~np.isnan( far_fields_array[:,0,...])).sum(axis=0)
    enhancement = near_fields_array -far_fields_array
    obs_baseline_mean_diff = np.nanmean( enhancement[:,0,...],axis=0)
    obs_baseline_std_diff = np.nanstd( enhancement[:,0,...],axis=0)
    sim_baseline_mean_diff = np.nanmean( enhancement[:,1,...],axis=0)
    sim_baseline_std_diff = np.nanstd( enhancement[:,1,...],axis=0)
    return obs_baseline_mean_diff, obs_baseline_std_diff, sim_baseline_mean_diff,\
        sim_baseline_std_diff, baseline_count
                         
def create_alerts_baseline( 
        domain_file: pathlib.Path,
        dir_list: list[str],
        obs_file_template: str = 'input/test_obs.pic.gz',
        sim_file_template: str = 'simulobs.pic.gz',
        near_threshold: float = 0.2,
        far_threshold: float = 1.0,
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
       near_threshold: distance from the target cell to be included in the near field
       far_threshold: distance from the target cell to be included in the far field
       output_file: name of output_file, will be overwritten if exists
    '''
    with xr.open_dataset( domain_file) as ds:
        logger.debug(f"Domain found at {domain_file}")

        dss = ds.load()
        n_cols = dss.sizes['COL']
        n_rows = dss.sizes['ROW']
        lats = dss['LAT'].to_numpy().squeeze()
        lons = dss['LON'].to_numpy().squeeze()
        land_mask = dss['LANDMASK'].to_numpy().squeeze()
        alerts_dims = ('ROW', 'COL')
    near_fields = []
    far_fields = []

    logger.info(f"Creating alerts baseline from {len(dir_list)} observations")

    for dir in dir_list:
        obs_list, sim_list, period_start, period_end = get_obs_sim(dir, obs_file_template, sim_file_template)
        obs_sim = [(o['latitude_center'], o['longitude_center'],
                    o['value'], s['value'],) for o,s in zip(obs_list, sim_list)]
        obs_sim_array = np.array( obs_sim)
        near, far = map_enhance(lats, lons, land_mask, obs_sim_array, near_threshold, far_threshold)
        near_fields.append( near)
        far_fields.append( far)

    logger.info(f"Constructing near_fields_array")
    near_fields_array = np.array(near_fields)

    logger.info(f"Constructing far_fields_array")
    far_fields_array = np.array( far_fields)


    obs_baseline_mean_diff, obs_baseline_std_diff, sim_baseline_mean_diff,\
        sim_baseline_std_diff, baseline_count =\
            calculate_baseline_statistics( near_fields_array, far_fields_array)

    logger.info(f"Creating dataset variables")
    dss['obs_baseline_mean_diff'] = xr.DataArray(obs_baseline_mean_diff, dims=alerts_dims)
    dss['obs_baseline_std_diff'] = xr.DataArray(obs_baseline_std_diff, dims=alerts_dims)
    dss['sim_baseline_mean_diff'] = xr.DataArray(sim_baseline_mean_diff, dims=alerts_dims)
    dss['sim_baseline_std_diff'] = xr.DataArray(sim_baseline_std_diff, dims=alerts_dims)
    dss['baseline_count'] = xr.DataArray(baseline_count, dims=alerts_dims)

    dss.attrs['alerts_near_threshold'] = near_threshold
    dss.attrs['alerts_far_threshold'] = far_threshold
    

    logger.info(f"Writing alerts baseline to {output_file}")
    dss.to_netcdf(output_file)

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
    with xr.open_dataset( baseline_file) as ds:
        logger.debug(f"Alerts baseline found at {baseline_file}")

        alerts_baseline_ds = ds.load()
        n_cols = alerts_baseline_ds.sizes['COL']
        n_rows = alerts_baseline_ds.sizes['ROW']
        resultShape = (n_rows, n_cols)
        lats = alerts_baseline_ds['LAT'].to_numpy().squeeze()
        lons = alerts_baseline_ds['LON'].to_numpy().squeeze()
        land_mask = alerts_baseline_ds['LANDMASK'].to_numpy().squeeze()
        baseline_mean = alerts_baseline_ds['sim_baseline_mean_diff'].to_numpy().squeeze()
        baseline_std = alerts_baseline_ds['obs_baseline_std_diff'].to_numpy().squeeze()

        near_threshold = alerts_baseline_ds.attrs['alerts_near_threshold']
        far_threshold = alerts_baseline_ds.attrs['alerts_far_threshold']
        ds.close()

    obs_list, sim_list, obs_period_start, obs_period_end = get_obs_sim(daily_dir, obs_file_template, sim_file_template)
    obs_sim = [(o['latitude_center'], o['longitude_center'],
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
    alerts[defined_mask] = (
        (np.abs( obs_enhancement - baseline_mean)[defined_mask] > significance_threshold *
         baseline_std[defined_mask]) &
        (np.abs( obs_enhancement -baseline_mean)[defined_mask] >
         alerts_threshold)).astype('float')

    logger.info(f"Writing alerts to {output_file}")

    # observations have specific times, but represent all the observations
    # that were available for the entire day, so make the period the full day
    period_start = obs_period_start.replace(hour=0, minute=0, second=0, microsecond=0)
    # end of day
    period_end = obs_period_end.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)

    # create a variable with projection coordinates
    projection_x = alerts_baseline_ds.XORIG + (0.5 * alerts_baseline_ds.XCELL) + np.arange(len(alerts_baseline_ds.COL)) * alerts_baseline_ds.XCELL
    projection_y = alerts_baseline_ds.YORIG + (0.5 * alerts_baseline_ds.YCELL) + np.arange(len(alerts_baseline_ds.ROW)) * alerts_baseline_ds.YCELL

    # copy dimensions and attributes from the alerts baseline, as the alerts
    # should be provided in the same grid / format
    # TODO: move most of this to the construction of the alerts_baseline output
    alerts_ds = xr.Dataset(
        data_vars={
            # meta data
            "lat": (("y", "x"), alerts_baseline_ds.variables["LAT"][0], {
                "long_name": "latitude",
                "units": "degrees_north",
                "standard_name": "latitude",
                "bounds": "lat_bounds",
            }),
            "lon": (("y", "x"), alerts_baseline_ds.variables["LON"][0], {
                "long_name": "longitude",
                "units": "degrees_east",
                "standard_name": "longitude",
                "bounds": "lon_bounds",
            }),
            # https://cfconventions.org/Data/cf-conventions/cf-conventions-1.11/cf-conventions.html#cell-boundaries
            "lat_bounds": (("y", "x", "cell_corners"), extract_bounds(alerts_baseline_ds.variables["LATD"][0][0])),
            "lon_bounds": (("y", "x", "cell_corners"), extract_bounds(alerts_baseline_ds.variables["LOND"][0][0])),
            # https://cfconventions.org/Data/cf-conventions/cf-conventions-1.11/cf-conventions.html#_lambert_conformal
            "grid_projection": ((), False, {
                "grid_mapping_name": "lambert_conformal_conic",
                "standard_parallel": (alerts_baseline_ds.TRUELAT1, alerts_baseline_ds.TRUELAT2),
                "longitude_of_central_meridian": alerts_baseline_ds.STAND_LON,
                "latitude_of_projection_origin": alerts_baseline_ds.MOAD_CEN_LAT,
            }),
            "projection_x": (("x"), projection_x, {
                "long_name": "x coordinate of projection",
                "units": "m",
                "standard_name": "projection_x_coordinate",
            }),
            "projection_y": (("y"), projection_y, {
                "long_name": "y coordinate of projection",
                "units": "m",
                "standard_name": "projection_y_coordinate",
            }),
            "time_bounds": (("time", "bounds_t"), [[period_start, period_end]]),

            # copied data
            "landmask": (("y", "x"), alerts_baseline_ds.variables['LANDMASK'][0], {
                "long_name": alerts_baseline_ds.variables['LANDMASK'].attrs['var_desc'],
                "standard_name": "land_binary_mask",
            }),
            "obs_baseline_mean_diff": (("time", "y", "x"), [alerts_baseline_ds.variables["obs_baseline_mean_diff"]], {
                "long_name": "Average observed difference between near and far field concentrations",
                "units": "ppb",
            }),
            "obs_baseline_std_diff": (("time", "y", "x"), [alerts_baseline_ds.variables["obs_baseline_std_diff"]], {
                "long_name": "Standard deviation of observed difference between near and far field concentrations",
                "units": "ppb",
            }),
            "sim_baseline_mean_diff": (("time", "y", "x"), [alerts_baseline_ds.variables["sim_baseline_mean_diff"]], {
                "long_name": "Average simulated difference between near and far field concentrations'",
                "units": "ppb",
            }),
            "sim_baseline_std_diff": (("time", "y", "x"), [alerts_baseline_ds.variables["sim_baseline_std_diff"]], {
                "long_name": "Standard deviation of simulated difference between near and far field concentrations",
                "units": "ppb",
            }),

            # results data
            "alerts": (("time", "y", "x"), [alerts], {
                "long_name": "Boolean flag for anomalous concentration",
                "missing_value": np.nan,
            }),
            "obs_enhancement": (("time", "y", "x"), [obs_enhancement], {
                "long_name": "Difference between near and far field concentrations",
                "units": "ppb",
            })
        },
        coords={
            "x": alerts_baseline_ds.coords["x"],
            "y": alerts_baseline_ds.coords["y"],
            "time": (("time"), [period_start], { "bounds": "time_bounds" }),
        },
        attrs={
            "DX": alerts_baseline_ds.DX,
            "DY": alerts_baseline_ds.DY,
            "XCELL": alerts_baseline_ds.XCELL,
            "YCELL": alerts_baseline_ds.YCELL,
            "alerts_near_threshold": alerts_baseline_ds.alerts_near_threshold,
            "alerts_far_threshold": alerts_baseline_ds.alerts_far_threshold,

            # common
            "title": "Open Methane daily methane alerts",
            "openmethane_version": os.getenv("OPENMETHANE_VERSION", "development"),
            "history": "",
        },
    )

    # ensure time and time_bounds use the same time encoding
    time_encoding = f"days since {period_start.strftime('%Y-%m-%d')}"
    alerts_ds.time.encoding["units"] = time_encoding
    alerts_ds.time_bounds.encoding["units"] = time_encoding

    alerts_ds.to_netcdf(output_file)


def map_enhance(lat, lon, land_mask, concs, nearThreshold, farThreshold):
    logger.debug("Calculating enhancements in map_enhance")
    nConcs = concs.shape[1]-2 # number of concentration records, the -2 removes lat,lon
    n_rows = land_mask.shape[0]
    n_cols = land_mask.shape[1]
    resultShape = (nConcs, n_rows, n_cols)
    near_field = np.zeros( resultShape)
    near_field[...] = np.nan
    far_field = np.zeros( resultShape)
    far_field[...] = np.nan


    # now build the input queue for multiprocessing points
    logger.debug(f"Building input_proc_list for shape {resultShape}")
    input_proc_list = []
    for i,j in itertools.product(range(0,n_rows,1), range(0, n_cols,1)):
        if land_mask[ i,j] > 0.5: # land point
            input_proc_list.append(( i, j, lat, lon, land_mask, concs,\
                          nearThreshold, farThreshold))

    nCPUs = int(os.environ.get('NCPUS', '1'))
    logger.debug(f"Spawning {nCPUs} processes")
    with multiprocessing.Pool( nCPUs) as pool:
        processOutput = pool.imap_unordered( point_enhance, input_proc_list)
        for obs in processOutput:
            i, j = obs[0:2]
            near_field[:, i, j], far_field[:, i, j] = obs[2:]
    return  near_field, far_field

def point_enhance( val):
    i, j, lat, lon, land_mask, concs, nearThreshold, farThreshold = val
    logger.debug(f"[Cell ({i}, {j})] Calculating point enhancement")

    if land_mask[i,j] < 0.5: # ocean point
        return i,j,np.nan,np.nan
    else:
        dist = calc_dist( concs, (lat[i,j], lon[i,j]))
        near = dist < nearThreshold
        far = (dist > nearThreshold ) & (dist < farThreshold)
        nearCount = near.sum()
        farCount = far.sum()
        if ( nearCount == 0) or (farCount == 0):
            return i,j,np.nan,np.nan
        else:
            near_field = concs[near,2:].mean( axis=0)
            far_field = concs[far,2:].mean( axis=0)
            return i,j, near_field, far_field


def calc_dist( concs, loc):
    diff = concs[:, 0:2] -np.array(loc)
    dist = (diff[:,0]**2 + diff[:,1]**2)**0.5
    return dist
